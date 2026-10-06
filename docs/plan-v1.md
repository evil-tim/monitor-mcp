# monitor-mcp v1 - locked design

## The problem

Situational awareness over the PSE and the Philippine and world economies was spread across
three systems: the Libram MCP (prices, portfolios), the Viber broker feeds (narrative), and a
wiki with 596 markdown files. The wiki accumulated *knowledge* well and produced *snapshots*
well, but had no layer that tracked whether its own standing claims still held.

It did have a monitoring instrument: `queries/future-events-monitoring-dashboard-2026.md`,
40 numbered rows with a documented column contract, named sources, cadences, thresholds and
per-entity consequences. Nothing evaluated it. Row 28's last reading was dated April 28 while
the file's frontmatter claimed a September update.

## The medium decision

| Option | Verdict |
|---|---|
| Markdown table | **Rejected.** Cannot reject a write, only display one. Every rule is a convention that fails silently. The source already showed the symptoms: two `CATEGORY 9` sections, one row with 6 cells instead of 7 |
| Spreadsheet | **Rejected as a store.** A cell boundary is a boundary, not a check. Demonstrated: a byte-identical corrupted grid was accepted whole by a naive importer and rejected 3-for-3 by a validated one. Data validation in Excel/Sheets is advisory and bypassable by paste |
| SQLite + constraints + triggers | **Chosen.** Enforcement applies to every writer at write time. Embedded, transactional, zero dependencies (stdlib `sqlite3`) |
| PostgreSQL + leases | Rejected for v1. Correct for multi-writer/high-frequency; this is ~40 rows with one writer, and provisioning Postgres in this container previously destabilised it |
| Spreadsheet as an *interface* | Rejected as not worth the round-trip contract. The store is the product |

Markdown is retained where it is good: prose synthesis in the wiki. What left the wiki is the
**structured** content, not the analysis.

## Drift mode -> constraint

| Drift mode | In markdown | Now |
|---|---|---|
| Duplicate/reused identity | hand-numbered; already collided | `PRIMARY KEY` + `UNIQUE(slug)` |
| Row that is not checkable | blank or vague cell | per-kind `CHECK`: threshold needs op+value, event needs a date, qualitative needs `review_by` |
| Threshold the engine cannot parse | free prose | closed `op` vocabulary |
| Category typo | silently a new section | `CHECK category IN (...)` |
| Reading with no provenance | implied in prose | `NOT NULL` method/confidence, plus in-code attribution rule |
| Status outside the vocabulary | free text | `CHECK status IN (...)` |
| Corrections rewriting history | edit in place | `BEFORE UPDATE` trigger -> ABORT |
| Deleting an inconvenient row | just delete it | `BEFORE DELETE` trigger -> ABORT |
| Renumbering | "row 11 retitled", "row 27 recalibrated" | slug immutable trigger |
| Impact naming a ticker that does not exist | free text | FK -> `entity(ticker)` |
| Duplicate reading for one slot | re-run appends again | `UNIQUE(signal_id, slot)` |
| Silent carry-forward | invisible | `UNVERIFIED` is a stored, first-class status |
| Two sources of truth | framework + dashboard drift apart | one table; the document is a render |

## Three tiers of column

Prose and constraints are not in tension. The rule is: **constrain what the machine reads,
free-text what only the human reads.**

| Tier | Columns | Constraint |
|---|---|---|
| Identity and semantics | slug, category, cadence, kind, op, threshold_num, mode | closed vocabularies, CHECK |
| Narrative | `rationale` (stable), `reading.note` (volatile) | unbounded TEXT, never parsed |
| Derived | state, overdue_days, staleness | computed at query time, never stored |

## Derived states

`NEVER_READ`, `CURRENT`, `STALE`, `TRIGGERED`, `DUE_SOON`, `DUE_EVENT`, `DUE_REVIEW`, `RETIRED`.

Precedence is deliberate: RETIRED beats everything, then NEVER_READ, then TRIGGERED (an alert
outranks a staleness complaint), then kind-specific date rules, then cadence staleness.

## Scope of v1

**In:** the store, the schema, the 40-row seed, DUE computation, the status render, the MCP tool
surface, and a test suite that asserts each guardrail rejects something.

**Out, deliberately:**

- **No resolvers.** Every row is `mode='manual'`. Nothing is auto-read. The store proves itself
  before anything is trusted to write to it automatically.
- **No alerting.** No Discord notification, no cron. Add once the store has demonstrated it
  holds.
- **No cron.** The database holds `cadence` as the schedule of record; cron is only a clock.

## Deferred: the resolver taxonomy

When resolvers are added, they split by class, and the server is the **enforcement boundary**
rather than the compute:

| Class | Rows | Who resolves | Why |
|---|---|---|---|
| `libram:` / `api:` | 2 | server, deterministically | cheap, repeatable, no model in the loop |
| `calendar:` | 8 | server computes DUE, agent confirms landing | date arithmetic is mechanical; "did it land" is not |
| `web:` | 13 | agent, validated write-back | bot walls, prose-to-number |
| `manual:` | 17 | agent, validated write-back | requires reading a filing |

Rules to carry into that work:

1. **`mark_unverified` must stay as easy to call as `record_reading`.** If the only pleasant
   path is to record something, values get invented.
2. **method/resolver consistency**: a resolver-bound row must not be writable by hand with a
   different method, or a guess gets laundered into the primary track.
3. **Graduation, not launch**: each web resolver starts `manual`, moves to `dry-run`, and reaches
   `auto` only after N consecutive reads that match a human spot-check. Scraped sources fail
   silently.
4. **Bounded runs**: `list_due(limit)` exists because a cron run has a finite iteration budget.
   Process the most urgent, let the rest roll.

## Verification

`uv run pytest` asserts, among other things, that 21 schema and trigger guardrails each reject a
violation, and that 7 in-code rules each reject a violation. The suite exists because a
validator that silently no-ops manufactures confidence.

Docker image build and compose startup are unverified from inside the Hermes container, which
has no Docker daemon.

## Open questions

Carried from `tools/EXTRACTION_REPORT.md`:

1. `PH1` was used as an entity in legacy rows 26 and 40 but was not a recognisable code; seeded as
   unresolved rather than guessed. **Resolved 2026-10-06:** PH1 World Developers, Inc., Megawide's
   real-estate subsidiary (unlisted).
2. The registry says `ICTSI`; Libram says `ICT`. Recorded in `entity.libram_code`.
3. `NGCP` is not PSE-listed but the registry treats it as an entity.
4. `review_by` on the 10 qualitative rows is a placeholder (today + 180 days), not an operator
   decision.
5. Tier and compound conditions survive as prose in the source. Tiers were extracted into
   `signal_tier`; compound conditions were **not** extracted into `signal_compound`, which is
   empty. Rows 1, 3 and 7 are known compound candidates.
6. The wiki framework file (`future-events-monitoring-framework-2026.md`, 1513 lines, 16 inbound
   links) is to have its per-category prose migrated into the entity and concept pages that carry
   each thesis, and then be archived. That is a separate workstream.
