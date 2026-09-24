"""The store: schema application, plus every read and write in the system.

This module is the enforcement boundary. Nothing else here issues SQL, and no tool exposes
raw SQL, because a raw-query tool would reintroduce every failure the DDL exists to prevent.
Rules the DDL cannot express - cross-field validation, provenance, slot arithmetic - live in
`_validate_reading`, and every rule in this file has a test asserting it actually fires.

A validator that silently no-ops is worse than no validator, because it manufactures
confidence. That is why tests/test_guardrails.py asserts each one REJECTS something.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

from . import config, models

ROW_SQL = """
SELECT s.id, s.slug, s.category, s.description, s.source, s.cadence, s.kind, s.op,
       s.threshold_num, s.due_date, s.review_by, s.mode, s.legacy_row, s.rationale,
       l.slot        AS last_slot,
       l.checked_at  AS last_checked_at,
       l.value_num   AS value_num,
       l.raw_text    AS raw_text,
       l.status      AS last_status,
       l.method      AS last_method,
       l.confidence  AS last_confidence,
       l.source_url  AS last_source_url,
       l.note        AS last_note
FROM signal s
LEFT JOIN v_latest_reading l ON l.signal_id = s.id
"""


# ---------------------------------------------------------------- connection / schema
def connect(path: str | Path | None = None) -> sqlite3.Connection:
    p = Path(path or config.db_path())
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), isolation_level=None)   # autocommit; explicit BEGIN where needed
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    # one long-lived writer with many readers: WAL plus a busy timeout is the whole
    # concurrency story, and no lease protocol is needed for a single-writer collector
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con


def migrate(con: sqlite3.Connection) -> list[int]:
    """Apply numbered migrations in order, one transaction each."""
    con.execute("""CREATE TABLE IF NOT EXISTS schema_version(
                     version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)""")
    applied = {r[0] for r in con.execute("SELECT version FROM schema_version")}
    done: list[int] = []
    for f in sorted(config.migrations_dir().glob("*.sql")):
        version = int(f.name.split("_", 1)[0])
        if version in applied:
            continue
        now = dt.datetime.now(config.MANILA).isoformat(timespec="seconds")
        # a half-applied schema is worse than none, so wrap the whole file and the version
        # bump in a single transaction
        con.executescript(
            f"BEGIN;\n{f.read_text()}\n"
            f"INSERT INTO schema_version VALUES({version}, '{now}');\nCOMMIT;"
        )
        done.append(version)
    return done


def schema_version(con: sqlite3.Connection) -> int | None:
    try:
        return con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    except sqlite3.OperationalError:
        return None


def initialised(con: sqlite3.Connection) -> bool:
    row = con.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='signal'").fetchone()
    return bool(row[0])


# ---------------------------------------------------------------- seed
def seed(con: sqlite3.Connection) -> dict:
    """Idempotent: upsert on ticker and slug.

    The seed is data applied through the same DDL the tools write through, so a malformed
    seed row is REJECTED rather than loaded.
    """
    from . import seed_signals

    now = dt.datetime.now(config.MANILA).isoformat(timespec="seconds")
    for e in seed_signals.ENTITIES:
        con.execute(
            """INSERT INTO entity(ticker, name, feed, libram_code) VALUES(?,?,?,?)
               ON CONFLICT(ticker) DO UPDATE SET name=excluded.name, feed=excluded.feed,
                                                 libram_code=excluded.libram_code""",
            (e["ticker"], e["name"], e["feed"], e["libram_code"]))

    for s in seed_signals.SIGNALS:
        con.execute(
            """INSERT INTO signal(slug, category, description, source, cadence, kind, op,
                                  threshold_num, due_date, review_by, mode, legacy_row,
                                  rationale, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,'manual',?,?,?,?)
               ON CONFLICT(slug) DO UPDATE SET
                 category=excluded.category, description=excluded.description,
                 source=excluded.source, cadence=excluded.cadence, kind=excluded.kind,
                 op=excluded.op, threshold_num=excluded.threshold_num,
                 due_date=excluded.due_date, review_by=excluded.review_by,
                 legacy_row=excluded.legacy_row, updated_at=excluded.updated_at""",
            (s["slug"], s["category"], s["description"], s["source"], s["cadence"],
             s["kind"], s["op"], s["threshold_num"], s["due_date"], s["review_by"],
             s["legacy_row"], s["rationale"], now, now))
        sid = con.execute("SELECT id FROM signal WHERE slug=?", (s["slug"],)).fetchone()[0]

        for level, tier in enumerate(s.get("tiers") or [], start=1):
            con.execute(
                """INSERT INTO signal_tier(signal_id, level, label, op, threshold_num)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(signal_id, level) DO UPDATE SET label=excluded.label,
                     op=excluded.op, threshold_num=excluded.threshold_num""",
                (sid, level, tier["label"], tier["op"], tier["value"]))

        for ticker, direction in (s.get("impacts") or {}).items():
            known = con.execute("SELECT 1 FROM entity WHERE ticker=?", (ticker,)).fetchone()
            if not known:
                continue      # unresolved code: skipped rather than invented as an entity
            con.execute(
                """INSERT OR IGNORE INTO signal_impact(signal_id, ticker, direction)
                   VALUES(?,?,?)""",
                (sid, ticker, direction if direction in ("up", "down") else "flat"))

    return {"entities": len(seed_signals.ENTITIES), "signals": len(seed_signals.SIGNALS)}


# ---------------------------------------------------------------- derived state
def _decorate(row: sqlite3.Row, now: dt.datetime) -> dict:
    r = dict(row)
    r["state"] = models.derive_state(
        mode=r["mode"], cadence=r["cadence"], kind=r["kind"], due_date=r["due_date"],
        review_by=r["review_by"], last_slot=r["last_slot"], last_status=r["last_status"],
        now=now, due_horizon_days=config.due_horizon_days())
    r["overdue_days"] = models.overdue_days(cadence=r["cadence"], last_slot=r["last_slot"], now=now)
    return r


def all_rows(con: sqlite3.Connection, now: dt.datetime | None = None) -> list[dict]:
    now = now or dt.datetime.now(config.MANILA)
    return [_decorate(r, now) for r in con.execute(ROW_SQL)]


def _signal(con: sqlite3.Connection, slug: str) -> dict | None:
    r = con.execute("SELECT * FROM signal WHERE slug=?", (slug,)).fetchone()
    return dict(r) if r else None


def state_of(con: sqlite3.Connection, slug: str, now: dt.datetime | None = None) -> str | None:
    now = now or dt.datetime.now(config.MANILA)
    for r in all_rows(con, now):
        if r["slug"] == slug:
            return r["state"]
    return None


# ---------------------------------------------------------------- reads
def list_due(con: sqlite3.Connection, limit: int = 10,
             now: dt.datetime | None = None) -> list[dict]:
    """Rows needing attention, most urgent first, capped at `limit`.

    The cap is not decoration: a cron run has a bounded iteration budget, so the caller
    processes the N most urgent and lets the rest roll to the next tick rather than
    timing out mid-sweep.
    """
    now = now or dt.datetime.now(config.MANILA)
    rows = [r for r in all_rows(con, now) if r["state"] in models.NEEDS_ATTENTION]
    rank = {models.NEVER_READ: 0, models.TRIGGERED: 1, models.DUE_EVENT: 2,
            models.DUE_REVIEW: 3, models.STALE: 4, models.DUE_SOON: 5}
    rows.sort(key=lambda r: (rank.get(r["state"], 9), -(r["overdue_days"] or 0.0), r["slug"]))
    return rows[:limit]


def get_signal(con: sqlite3.Connection, slug: str, readings: int = 20,
               now: dt.datetime | None = None) -> dict | None:
    now = now or dt.datetime.now(config.MANILA)
    sig = _signal(con, slug)
    if sig is None:
        return None
    row = next((r for r in all_rows(con, now) if r["slug"] == slug), None)
    sig["tiers"] = [dict(t) for t in con.execute(
        "SELECT level, label, op, threshold_num FROM signal_tier WHERE signal_id=? ORDER BY level",
        (sig["id"],))]
    sig["impacts"] = [dict(i) for i in con.execute(
        """SELECT i.ticker, i.direction, e.name, e.libram_code
           FROM signal_impact i JOIN entity e ON e.ticker=i.ticker
           WHERE i.signal_id=? ORDER BY i.ticker""", (sig["id"],))]
    sig["labels"] = [r[0] for r in con.execute(
        """SELECT label FROM signal_label WHERE signal_id=? ORDER BY label""", (sig["id"],))]
    sig["state"] = row["state"] if row else None
    sig["overdue_days"] = row["overdue_days"] if row else None
    sig["readings"] = [dict(r) for r in con.execute(
        """SELECT slot, checked_at, value_num, raw_text, status, method, confidence,
                  source_url, note
           FROM reading WHERE signal_id=? ORDER BY slot DESC, id DESC LIMIT ?""",
        (sig["id"], readings))]
    return sig


def status(con: sqlite3.Connection, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(config.MANILA)
    if not initialised(con):
        return {"error": "schema not initialised", "hint": "call init()", "db_path": str(config.db_path())}
    rows = all_rows(con, now)
    by_state: dict[str, int] = {}
    for r in rows:
        by_state[r["state"]] = by_state.get(r["state"], 0) + 1
    return {
        "db_path": str(config.db_path()),
        "schema_version": schema_version(con),
        "signals": con.execute("SELECT COUNT(*) FROM signal").fetchone()[0],
        "entities": con.execute("SELECT COUNT(*) FROM entity").fetchone()[0],
        "readings": con.execute("SELECT COUNT(*) FROM reading").fetchone()[0],
        "retired": con.execute("SELECT COUNT(*) FROM signal WHERE mode='retired'").fetchone()[0],
        "by_kind": {k: sum(1 for r in rows if r["kind"] == k) for k in models.KINDS},
        "by_cadence": {c: sum(1 for r in rows if r["cadence"] == c) for c in models.CADENCES},
        "by_state": by_state,
        "never_read": by_state.get(models.NEVER_READ, 0),
        "rows": rows,
    }


# ---------------------------------------------------------------- write validation
def _validate_reading(sig: dict, *, status: str, method: str, confidence: str,
                      value_num: float | None, source_url: str | None,
                      note: str | None) -> list[str]:
    """Rules the DDL cannot express. Each returns a human-readable reason."""
    errs: list[str] = []
    if status not in models.STATUSES:
        errs.append(f"status {status!r} is not one of {list(models.STATUSES)}")
    if method not in models.METHODS:
        errs.append(f"method {method!r} is not one of {list(models.METHODS)}")
    if confidence not in models.CONFIDENCES:
        errs.append(f"confidence {confidence!r} is not one of {list(models.CONFIDENCES)}")

    if status == "UNVERIFIED":
        # the honest path must be as easy as the productive one, or the value gets invented
        if not note:
            errs.append("an UNVERIFIED reading requires a note saying why nothing could be read")
        if confidence == "primary":
            errs.append("an UNVERIFIED reading cannot carry primary confidence: "
                        "you cannot be certain about not having read it")

    if status in ("OK", "TRIGGERED") and sig["kind"] == "threshold" and value_num is None:
        errs.append(f"row {sig['legacy_row']} is kind='threshold', so status {status} "
                    "requires value_num")

    if confidence == "primary" and not source_url and method != "libram":
        errs.append("primary confidence requires an attributable source: a source_url, "
                    "or method='libram' for the in-house feed")

    if sig["mode"] == "retired":
        errs.append(f"row {sig['legacy_row']} is retired; unretire it before recording a reading")
    return errs


def record_reading(con: sqlite3.Connection, slug: str, *, status: str = "OK",
                   method: str = "manual", confidence: str = "primary",
                   value_num: float | None = None, raw_text: str | None = None,
                   source_url: str | None = None, note: str | None = None,
                   when: dt.datetime | None = None,
                   slot: str | None = None) -> dict:
    when = when or dt.datetime.now(config.MANILA)
    sig = _signal(con, slug)
    if sig is None:
        return {"error": f"unknown signal slug: {slug!r}",
                "hint": "list_due() and status() show the slugs that exist"}

    errs = _validate_reading(sig, status=status, method=method, confidence=confidence,
                             value_num=value_num, source_url=source_url, note=note)
    if errs:
        return {"error": "validation failed", "slug": slug, "reasons": errs}

    slot = slot or models.slot_for(sig["cadence"], when)
    try:
        cur = con.execute(
            """INSERT INTO reading(signal_id, slot, checked_at, value_num, raw_text, status,
                                  method, confidence, source_url, note)
               VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (sig["id"], slot, when.isoformat(timespec="seconds"), value_num, raw_text,
             status, method, confidence, source_url, note))
    except sqlite3.IntegrityError as e:
        return {"error": "rejected by the store", "reason": str(e), "slug": slug, "slot": slot}

    return {"ok": True, "slug": slug, "slot": slot, "reading_id": cur.lastrowid,
            "state": state_of(con, slug, when)}


def mark_unverified(con: sqlite3.Connection, slug: str, reason: str, *,
                    method: str = "manual", source_url: str | None = None,
                    confidence: str = "secondary", when: dt.datetime | None = None,
                    slot: str | None = None) -> dict:
    """Record that a row could NOT be read.

    A first-class outcome, not a failure: an instrument that cannot distinguish
    'nothing changed' from 'I could not look' is lying to its reader.
    """
    return record_reading(con, slug, status="UNVERIFIED", method=method,
                          confidence=confidence, note=reason, source_url=source_url,
                          when=when, slot=slot)


# ---------------------------------------------------------------- spec changes
def add_signal(con: sqlite3.Connection, slug: str, *, category: str, description: str,
               source: str, cadence: str, kind: str, op: str | None = None,
               threshold_num: float | None = None, due_date: str | None = None,
               review_by: str | None = None, legacy_row: int | None = None,
               rationale: str | None = None, mode: str = "manual") -> dict:
    errs: list[str] = []
    if category not in models.CATEGORIES:
        errs.append(f"category {category!r} is not one of {list(models.CATEGORIES)}")
    if cadence not in models.CADENCES:
        errs.append(f"cadence {cadence!r} is not one of {list(models.CADENCES)}")
    if kind not in models.KINDS:
        errs.append(f"kind {kind!r} is not one of {list(models.KINDS)}")
    if mode not in models.MODES:
        errs.append(f"mode {mode!r} is not one of {list(models.MODES)}")
    if kind == "threshold" and (op is None or threshold_num is None):
        errs.append("kind='threshold' requires both op and threshold_num")
    if op is not None and op not in models.OPS:
        errs.append(f"op {op!r} is not one of {list(models.OPS)}")
    if kind == "event" and not due_date:
        errs.append("kind='event' requires due_date (otherwise it is kind='qualitative')")
    if kind == "qualitative" and not review_by:
        errs.append("kind='qualitative' requires review_by")
    if errs:
        return {"error": "validation failed", "reasons": errs}

    now = dt.datetime.now(config.MANILA).isoformat(timespec="seconds")
    try:
        cur = con.execute(
            """INSERT INTO signal(slug, category, description, source, cadence, kind, op,
                                  threshold_num, due_date, review_by, mode, legacy_row,
                                  rationale, created_at, updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (slug, category, description, source, cadence, kind, op, threshold_num,
             due_date, review_by, mode, legacy_row, rationale, now, now))
    except sqlite3.IntegrityError as e:
        return {"error": "rejected by the store", "reason": str(e)}
    return {"ok": True, "slug": slug, "id": cur.lastrowid}


def retire_signal(con: sqlite3.Connection, slug: str, reason: str) -> dict:
    """Rows are retired, never deleted: the history stays, the row leaves scope."""
    cur = con.execute(
        "UPDATE signal SET mode='retired', updated_at=? WHERE slug=? AND mode<>'retired'",
        (dt.datetime.now(config.MANILA).isoformat(timespec="seconds"), slug))
    if cur.rowcount == 0:
        return {"error": "no active signal with that slug", "slug": slug}
    return {"ok": True, "slug": slug, "retired": True, "note": reason}


def label_signal(con: sqlite3.Connection, slug: str, labels: list[str],
                 kind: str = "tag") -> dict:
    """Free-form taxonomy. Labels are data, not structure, so regrouping cannot desynchronise."""
    sig = _signal(con, slug)
    if sig is None:
        return {"error": f"unknown signal slug: {slug!r}"}
    for lab in labels:
        con.execute("INSERT OR IGNORE INTO label(label, kind) VALUES(?,?)", (lab, kind))
    con.execute("DELETE FROM signal_label WHERE signal_id=?", (sig["id"],))
    for lab in labels:
        con.execute("INSERT OR IGNORE INTO signal_label(signal_id, label) VALUES(?,?)",
                    (sig["id"], lab))
    return {"ok": True, "slug": slug, "labels": sorted(labels)}
