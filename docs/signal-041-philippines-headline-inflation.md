# Signal 041 — `philippines-headline-inflation`

Operator-approved spec record. Written 2026-10-06.

## Why this file exists

Row 41 was added to the **live store** through the `add_signal` tool. That tool cannot set
`impacts` or `tiers` — those two tables are written **only** by `store.seed()`, driven by the
generated `monitor_mcp/seed_signals.py`. The seed cannot currently be regenerated either:
`tools/extract_registry.py` reads `queries/future-events-monitoring-dashboard-2026.md`, and that
file is now a `render_status()` **artifact**, not the original 7-column extraction table.

So there is no live path from an approved impact/tier decision to the store. This file is that
missing path's stand-in: the approved values are recorded here so they survive until a wiring
mechanism exists, and so whoever wires them does not have to re-derive them. Future tool-added
rows get their own `signal-NNN-<slug>.md` alongside this one.

**Status 2026-10-06: locked in and wired via the seed (Option B below).** Both child tables are
now populated from `monitor_mcp/seed_signals.py`, and the suite asserts it
(`tests/test_seed.py::test_tool_added_row_carries_its_impacts_and_tiers`). The live database picks
them up on the next host-side `init`.

## The row as it exists in the store

| Field | Value |
|---|---|
| id | 41 |
| slug | `philippines-headline-inflation` |
| category | Macro |
| description | Philippines headline CPI inflation (YoY, %) |
| source | PSA monthly CPI release |
| cadence | monthly |
| kind | threshold |
| predicate | `> 4.0` |
| mode | manual |
| legacy_row | NULL — not one of the legacy dashboard rows 1–40 |
| created_at | 2026-10-06T20:54:07+08:00 |

First reading (already recorded): slot `2026-10-01`, value **7.2**, status **TRIGGERED**,
method `fetch`, confidence `primary`, source the Philstar release URL.

## Impacts — approved 2026-10-06

Direction is the impact on the ticker **when the row triggers** (headline inflation above 4.0%,
i.e. above the BSP's 2–4% target band). `up` / `down` only; the seed vocabulary also has `flat`
(piped links) but it is unused.

| Ticker | Direction | Channel | Precedent in the existing seed |
|---|---|---|---|
| BPI | `down` | Above-target inflation drives the hike path; higher rates + credit-quality drag | Row 31 `bsp-policy-rate-trajectory` {BPI: down} |
| ACEN | `down` | Capital-heavy IPP; higher discount rate | Row 27 `us-10-yr-treasury-yield-bsp-rate-embi-spread` {ACEN: down} |
| CREC | `down` | Same rate/discount channel | Row 27 {CREC: down} |
| CREIT | `down` | Yield vehicle, rate-sensitive | Row 27 {CREIT: down} |
| MWIDE | `down` | Construction-input + financing costs | Row 38 `steel-rebar-construction-materials-price-index`; Row 28 {MWIDE: down} |
| ICTSI | `down` | Higher EMBI/rates + softer trade demand | Row 27 {ICTSI: down}; Row 34 `gdp-growth-loan-demand` {ICTSI: down} |
| **SCC** | **`up`** | Fossil-fuel inflation lifts scarcity pricing for a coal/power producer — hedged, weak positive | **Deliberate divergence from row 27** |

```python
'impacts': {'BPI': 'down', 'ACEN': 'down', 'CREC': 'down', 'CREIT': 'down',
            'MWIDE': 'down', 'ICTSI': 'down', 'SCC': 'up'},
```

### The SCC sign is intentional, not an error

Row 27 maps SCC `down` (financial-conditions channel: higher yields, higher discount rate). This
row maps it `up` (real-economy channel: fossil-fuel inflation is the scarcity pricing a coal/power
producer is hedged against — see rows 1/2/3/7/8, all `up` for SCC). Same company, two channels,
opposite signs. Do not "fix" one to match the other.

### Parked (not approved, listed so they are not re-litigated from scratch)

| Ticker | Direction considered | Why it was left out |
|---|---|---|
| RCR | `down` | Grounded (row 23 consumer squeeze) but row 27 — the closest macro row — omits the REITs |
| AREIT | `down` | Grounded (rows 30/36) but likewise omitted from row 27 |
| OGP | `up` | Two hops (inflation → gold price → OGP); the channel is row 18, not inflation directly |

NGCP omitted (the seed maps it `up` only where it profits from grid delay — no coherent inflation
direction). PH1 omitted (unresolved code, never assigned).

## Tiers — approved 2026-10-06

Levels are ordered and stored in `signal_tier` keyed by `level` (1, 2, 3). Anchored to real
reference points rather than round numbers.

| Level | Label | Op | Value | Anchor |
|---|---|---|---|---|
| 1 | `Alert` | `>` | 4.0 | The BSP's formal target ceiling — the row's own threshold; band breach |
| 2 | `Stress` | `>` | 6.0 | The BSP's own 2026 forecast (6.1%), and the same numeric trigger row 31 uses |
| 3 | `Critical` | `>` | 7.0 | Multi-year-high territory (Apr 2026 peak 7.2%; Mar 2023 peak 7.6%) |

```python
'tiers': [{'label': 'Alert',    'op': '>', 'value': 4.0},
          {'label': 'Stress',   'op': '>', 'value': 6.0},
          {'label': 'Critical', 'op': '>', 'value': 7.0}],
```

The reading on record (7.2) sits in **Critical**.

**Not enforced.** Tiers are stored but no code path evaluates them — `tools/EXTRACTION_REPORT.md`
already flags this ("Tiers are carried in `tiers` and are not yet enforced"). Today they are
annotations, nothing more, and the label set is a convention this row is now anchored to rather
than a system guarantee.

## Wiring — done 2026-10-06 via Option B

| Option | What it is | Status |
|---|---|---|
| A — extend the tool surface | Add `impacts` and `tiers` params to `store.add_signal` / `server.add_signal`, with guardrail tests asserting each new rule rejects a bad value | **Not taken.** Remains the right fix for future rows — it would make impacts/tiers settable by tool so the seed stays the legacy-only artifact it now is |
| **B — hand-edit the seed** | Added this dict to `seed_signals.SIGNALS` with `legacy_row: None`; `PH1` resolved in the same pass | **Taken 2026-10-06.** Edits recorded in the seed's hand-amendment header, since the generator can no longer regenerate the file |

`init` is safe: `seed()` upserts on `slug`, `INSERT OR IGNORE`s impacts, upserts tiers by level,
and never touches readings. Row 41's existing reading survives the re-seed.

## Verified vs unverified

| Claim | Status |
|---|---|
| Row 41 exists in the live store (id 41, spec as tabulated above) | **verified** — `get_signal` |
| Reading 1 recorded (slot 2026-10-01, 7.2, TRIGGERED) | **verified** — `get_signal` |
| `add_signal` accepts no `impacts`/`tiers` argument | **verified** — read `monitor_mcp/server.py` |
| Only `store.seed()` writes `signal_impact` / `signal_tier` | **verified** — read `monitor_mcp/store.py` |
| `render.py` does not emit impacts, so the wiki dashboard cannot carry them | **verified** |
| Impacts present in the seed (`seed_signals.SIGNALS[40]`) | **verified** — parsed; suite green |
| Tiers present in the seed | **verified** — parsed; suite green |
| Seed loads both child tables via `seed()` | **verified** — `tests/test_seed.py`, 66 tests pass |
| PH1 resolved in the seed | **verified** — `test_ph1_is_the_resolved_real_estate_entity` |
| Impacts/tiers applied to the **live** store | **NOT yet** — needs a host-side `init` (no Docker daemon in this container) |
| Tiers evaluated by any code path | **NOT done** — stored-only, unenforced |
