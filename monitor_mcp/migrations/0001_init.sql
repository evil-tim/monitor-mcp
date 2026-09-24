
-- 0001_init.sql — the monitor registry.
--
-- Every constraint here exists to make a specific class of drift impossible rather than
-- merely detectable. docs/plan-v1.md maps drift mode -> constraint one for one.

-- NOTE: `schema_version` is created by the migration runner in store.migrate(), not here.
-- It has to exist before any migration runs, so it belongs to the runner rather than to a
-- migration. Creating it here too would fail on a fresh database.

-- The registry's own entity vocabulary, so signal_impact.ticker is a real foreign key
-- and a typo is rejected instead of becoming a new phantom entity.
CREATE TABLE entity (
  ticker      TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  feed        TEXT NOT NULL CHECK (feed IN ('libram','web','manual')),
  libram_code TEXT            -- NULL where the registry's code is not Libram's
);

CREATE TABLE signal (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  slug          TEXT NOT NULL UNIQUE,          -- stable identity; never renumbered
  category      TEXT NOT NULL CHECK (category IN
                  ('Grid','Market','Political','Supply','Financial','Infra','Execution','Macro','Labor')),
  description   TEXT NOT NULL,
  source        TEXT NOT NULL,
  cadence       TEXT NOT NULL CHECK (cadence IN ('daily','weekly','monthly','quarterly','event')),
  kind          TEXT NOT NULL CHECK (kind IN ('threshold','event','qualitative')),
  op            TEXT CHECK (op IN ('>=','<=','>','<','==')),
  threshold_num REAL,
  due_date      TEXT,
  review_by     TEXT,
  mode          TEXT NOT NULL DEFAULT 'manual'
                  CHECK (mode IN ('manual','dry-run','auto','retired')),
  legacy_row    INTEGER UNIQUE,                -- traceability to the wiki dashboard
  rationale     TEXT,                          -- free prose; stable narrative, never parsed
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  -- every row must be checkable in a way its own kind permits
  CHECK (kind <> 'threshold'   OR (op IS NOT NULL AND threshold_num IS NOT NULL)),
  CHECK (kind <> 'event'       OR due_date IS NOT NULL),
  CHECK (kind <> 'qualitative' OR review_by IS NOT NULL),
  -- nothing may claim to be auto-resolvable without a machine-comparable predicate
  CHECK (mode <> 'auto'        OR op IS NOT NULL)
);

CREATE TABLE signal_tier (
  signal_id     INTEGER NOT NULL REFERENCES signal(id),
  level         INTEGER NOT NULL,
  label         TEXT NOT NULL,
  op            TEXT NOT NULL CHECK (op IN ('>=','<=','>','<','==')),
  threshold_num REAL NOT NULL,
  PRIMARY KEY (signal_id, level)
);

CREATE TABLE signal_compound (
  signal_id   INTEGER NOT NULL REFERENCES signal(id),
  requires_id INTEGER NOT NULL REFERENCES signal(id),
  PRIMARY KEY (signal_id, requires_id),
  CHECK (signal_id <> requires_id)
);

CREATE TABLE signal_impact (
  signal_id INTEGER NOT NULL REFERENCES signal(id),
  ticker    TEXT    NOT NULL REFERENCES entity(ticker),
  direction TEXT    NOT NULL CHECK (direction IN ('up','down','flat')),
  PRIMARY KEY (signal_id, ticker)
);

-- free-form taxonomy: labels are data, not structure, so regroupings cannot desynchronise
CREATE TABLE label (
  label TEXT PRIMARY KEY,
  kind  TEXT NOT NULL DEFAULT 'tag'
);

CREATE TABLE signal_label (
  signal_id INTEGER NOT NULL REFERENCES signal(id),
  label     TEXT    NOT NULL REFERENCES label(label),
  PRIMARY KEY (signal_id, label)
);

CREATE TABLE reading (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id   INTEGER NOT NULL REFERENCES signal(id),
  slot        TEXT NOT NULL,        -- logical slot derived from cadence, not wall-clock
  checked_at  TEXT NOT NULL,
  value_num   REAL,                 -- the metric the predicate is written against
  raw_text    TEXT,                 -- verbatim what the source printed
  status      TEXT NOT NULL CHECK (status IN ('OK','TRIGGERED','UNVERIFIED','STALE','DUE','RETIRED')),
  method      TEXT NOT NULL CHECK (method IN ('libram','api','fetch','manual')),
  confidence  TEXT NOT NULL CHECK (confidence IN ('primary','secondary','proxy')),
  source_url  TEXT,
  note        TEXT,                 -- free prose; volatile commentary travels with the observation
  UNIQUE (signal_id, slot)          -- idempotency per logical slot
);

-- Append-only enforcement. Without these, a correction could rewrite history and the audit
-- trail would be whatever the last writer wanted it to be.
CREATE TRIGGER reading_no_update BEFORE UPDATE ON reading BEGIN
  SELECT RAISE(ABORT, 'readings are append-only: record a new slot instead of editing');
END;
CREATE TRIGGER reading_no_delete BEFORE DELETE ON reading BEGIN
  SELECT RAISE(ABORT, 'readings are append-only: delete is not permitted');
END;
CREATE TRIGGER signal_no_delete BEFORE DELETE ON signal BEGIN
  SELECT RAISE(ABORT, 'signals are never deleted: set mode=retired');
END;
CREATE TRIGGER signal_slug_immutable BEFORE UPDATE OF slug ON signal BEGIN
  SELECT RAISE(ABORT, 'signal slug is immutable: it is the stable identity');
END;

CREATE VIEW v_latest_reading AS
SELECT r.* FROM reading r
WHERE r.id = (SELECT r2.id FROM reading r2 WHERE r2.signal_id = r.signal_id
              ORDER BY r2.slot DESC, r2.id DESC LIMIT 1);
