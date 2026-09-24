# Next steps — the surrounding components

`docs/handoff.md` covers deployment and the wiki migration. This covers what gets built *around*
the store, in dependency order, with a definition of done for each phase.

## Component map

```
                    ┌─────────────────────────────┐
   Libram MCP ─────▶│                             │
   (prices, FX,     │        monitor-mcp          │
    funds, crypto)  │      (SQLite + FastMCP)     │
                    │                             │
   Viber feeds ────▶│  spec · readings · derived  │
   (broker narrative│         state               │
    + leads)        │                             │
                    └──────┬──────────────┬───────┘
                           │              │
              rendered status doc      list_due()
                           │              │
                           ▼              ▼
                    ┌───────────┐  ┌──────────────┐
                    │   wiki    │  │ cron jobs    │
                    │ (prose +  │◀─│ (the clock)  │
                    │  renders) │  └──────┬───────┘
                    └───────────┘         │
                                          ▼
                                   alerting (Discord)
                                  mechanical facts only
```

Read it as: the store is the only place state lives. Everything else reads from it or writes to
it through a validated tool.

## Phase order

| # | Phase | Depends on | Blocks |
|---|---|---|---|
| 0 | Deploy + register | — | 1, 3, 4 |
| 1 | Wiki migration + rendered status doc | 0 | 5 |
| 2 | Resolver layer (`libram:` rows only) | 0 | 4 |
| 3 | Alerting | 0, 1 | 4 |
| 4 | Cron jobs | 2, 3 | 5 |
| 5 | Web resolver graduation, row by row | 4 | 6 |
| 6 | Retire the legacy queries system as a store | 1, 5 | — |

Phases 1 and 2 are independent and can run in either order.

---

## Phase 2 — the resolver layer

Only **2 of the 40 rows** are Libram-resolvable, and both have a subtlety worth stating before
anyone writes code:

| Row | Registry says | Reality | Consequence |
|---|---|---|---|
| 28 `php-usd-spot-rate-trend` | BSP / BSP FX reserve data | Libram has USD/PHP daily since 2024-01-01 | Genuinely primary **for the rate** — but the predicate is 6-month depreciation, a *derived* metric, so the resolver must derive it, not pass the rate through |
| 18 `gold-spot-price-support` | London Metal Exchange | Libram's `XAU` is Gold-Ethereum via Chainlink | A **tokenised proxy**, not LME spot. `confidence='proxy'`, never `primary` |

That second row is the trap. A resolver that silently treats a tokenised gold feed as LME spot
would report `primary` confidence on a proxy — exactly the laundering the
method/resolver consistency rule exists to prevent.

**Consequences for schema.** Resolvers need a place to live. Two options, decide before coding:

1. Add a `resolver` and `resolver_config` column to `signal` (JSON or a small table), and have
   `mode='auto'` mean "the server derives this". Keeps one writer.
2. Keep resolvers in `monitor_mcp/resolvers/` as code addressed by name from `signal.source`.

Option 1 is stricter and testable from the database side; option 2 is simpler and keeps the DDL
untouched. Either way the reading must record which resolver produced it.

**Definition of done:** `refresh_auto()` — one tool call that resolves every `auto`-mode row
deterministically and returns only what changed — with a test per resolver against a recorded
fixture, and a test asserting a `proxy`-confidence resolver cannot write `primary`.

## Phase 3 — alerting

TRIGGERED notifies with **mechanical facts only**: row, metric, value, source URL, date, affected
tickers, and the threshold it crossed. No interpretation, no "this suggests", no auto-editing of
wiki theses.

Why this is a hard rule and not a preference: the weekly recap work deliberately retired a
sentiment composite (`pse-vibe-check`) because unfalsifiable outputs cannot be checked against
reality, so a dead signal goes unnoticed for weeks. An auto-generated interpretation would be
that same regression wearing a new costume. The instrument's entire value is that every output is
checkable against a dated source.

Deliver via the Discord webhook script (`~/.hermes/scripts/discord_webhook.py`, `send_text()` or
`DiscordEmbed`). Respect the 2,000-character limit; a notification is a pointer, not a report.

**Definition of done:** a TRIGGERED reading produces one message containing the source URL and the
threshold crossed, and a row that cannot be read produces **nothing** rather than a false all-clear.

## Phase 4 — cron jobs

The governing constraint is your environment, not the design: `HERMES_CRON_TIMEOUT` defaults to
600s (an *inactivity* limit, so the clock runs while a child blocks), `HERMES_MAX_ITERATIONS` is 60,
cron cannot create jobs, cannot ask questions, and passes `skip_memory=True`.

| Job | Cadence | Work |
|---|---|---|
| `monitor-refresh` | daily | `refresh_auto()` + `render_status()`. Two or three calls, no judgement |
| `monitor-due` | daily or weekly | `list_due(limit=N)`, work the rows, write back, notify on TRIGGERED |

**The database holds `cadence` as the schedule of record; cron is only the clock.** Do not encode
per-row schedules into cron expressions — that would create a second source of truth for cadence,
which is the failure mode this whole project exists to avoid.

**Why `list_due` takes a `limit`.** Twelve due rows at roughly two tool calls each (fetch, record)
is already ~24 calls, near half the 60-iteration budget. Process the N most urgent, let the rest
roll to the next tick: graceful degradation instead of a timeout. `NEVER_READ` ranks above `STALE`
deliberately — unknown outranks late.

Raise the ceiling with `HERMES_CRON_TIMEOUT=1800` in `$HERMES_HOME/.env` if a run genuinely needs
it; it requires a gateway restart.

**Definition of done:** two consecutive runs that complete inside budget, with the second reporting
fewer stale rows than the first (or an explicit UNVERIFIED for each one it could not read).

## Phase 5 — web resolver graduation

13 rows need web sources: PAGASA, NGCP, IEMOP/WESM, ERC, DOE, DBM, PSA, BSP, Fed, LME, shipping
insurance. These fail *silently* — a stale cache or a dead endpoint returns plausible data or an
error string, and the run still reports success.

**Graduate each row rather than launching them.** `mode` moves `manual → dry-run → auto`, and a row
reaches `auto` only after several consecutive dry-run reads that match a human spot-check. The
automatable rows are exactly the ones that go stale without complaining, so they have to earn it
individually.

Per-row cost is real: a parser, a recorded fixture, a test, and one manual verification. Budget it
as ~13 small pieces of work, not one project.

**Definition of done:** no row reaches `auto` without a fixture-backed test, and a resolver that
returns nothing writes `UNVERIFIED` rather than nothing at all.

## Phase 1 — wiki integration

- Write the `render_status()` output into the wiki as a clearly-banner-marked generated page. The
  hash header makes a hand edit detectable, so nobody "fixes" it by hand.
- Replace the legacy dashboard file's body with that same render, so its 2 inbound links keep working.
- Migrate the framework file per `docs/handoff.md` §B.
- Add monitoring slug lists to entity page frontmatter.

**Definition of done:** every entity page that has an impacted signal links to it; `wikilint`'s
broken-link count is unchanged as a delta; the archived shell is in `_archive/` and unwired.

## Phase 6 — retiring the legacy queries system

Being precise about what is retired, because the useful half survives:

| Retired | Kept |
|---|---|
| The registry as a markdown table | `queries/`, `comparisons/`, `concepts/` as **prose synthesis** |
| Hand-maintained "current status" sections | Dated snapshot pages (they are point-in-time by design) |
| Any document that restates what the store holds | Entity pages, which are the home for rationale |

The test: if a sentence is a *state* that goes stale silently, it belongs in the store. If it is an
*argument* that was true of a dated reading, it belongs in prose.

## Deferred and rejected, with reasons

| Idea | Verdict |
|---|---|
| CSV/spreadsheet as an interface | Rejected — not worth a round-trip contract when Python can query SQLite directly |
| Spreadsheet as the store | Rejected — a cell boundary is a boundary, not a check. Data validation in Sheets/Excel is advisory and a paste bypasses it |
| Sentiment / positioning composites | Rejected — the retired vibe-check. Unfalsifiable, so a dead signal goes unnoticed |
| Leases / multi-worker claim protocol | Not needed — single writer. `WAL` plus `busy_timeout=5000` is the whole concurrency story |
| PostgreSQL | Rejected for now — ~40 rows, one writer; provisioning Postgres in this container previously destabilised it. The SQL is ~90% portable if that changes |
| ORM / Alembic | Premature. Numbered `.sql` migrations are diffable and reviewable |
| Auto-trading, auto-editing theses | Out of scope permanently. The instrument detects; a human decides |

## The honest risk

The build has 64 passing tests and a proven constraint set, but **zero rows have been read against
their named sources**. Until phase 4 runs, the store's only output is "38 rows nobody has looked
at" — which is correct, and useful, and not the same as situational awareness. The value arrives
when readings start landing in it, and that is manual work before it is automated work.
