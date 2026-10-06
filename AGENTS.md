# AGENTS.md - module map, conventions, pitfalls

## Module map

| Module | Responsibility |
|---|---|
| `config.py` | env resolution, **lazily** inside each call. Never at import |
| `models.py` | vocabularies, `slot_for`, `derive_state`, `overdue_days` |
| `store.py` | **all** SQL in the system. Connect, migrate, seed, read, write, validate |
| `render.py` | the status document, hash-stamped so a hand edit is detectable |
| `server.py` | FastMCP tool surface. Thin wrappers; no business rules |
| `seed_signals.py` | **generated** by `tools/extract_registry.py`. Do not hand-edit |

## Conventions

- **Never add a raw-SQL tool.** The store is the enforcement boundary; a query tool would
  reintroduce every failure the DDL prevents.
- **Validation lives in `store._validate_reading` and the DDL, nowhere else.** `server.py` only
  translates arguments.
- **Readings are append-only.** Never add an UPDATE or DELETE path for them. To correct a
  reading, record a new slot.
- **The slot is derived from cadence, not `now()`.** That is what makes `UNIQUE(signal_id, slot)`
  collapse a retry instead of inventing a second reading.
- **Derived state is never stored on the signal row.** A stored status is a second source of
  truth that drifts from the readings it was derived from.
- **Rows are retired, never deleted.** The trigger enforces it.
- **Config is resolved per call.** The process must start with the database missing so `status`
  can explain the problem instead of dying at import.

## Pitfalls

1. **A validator that silently no-ops is worse than no validator.** The first draft of the CSV
   round-trip prototype had a str/int key mismatch that silently disabled a check; it was caught
   only by reading output that showed three defects where four were expected. Hence
   `tests/test_guardrails.py` asserts every rule **rejects** something rather than inspecting the
   schema and assuming it works. Add a test with every new rule.
2. **`legacy_row` is UNIQUE and load-bearing.** It is the traceability link back to the wiki
   dashboard. Re-seeding relies on `slug` being stable; renaming a slug orphans its readings'
   provenance in the reader's head, which is why a trigger forbids it.
3. **The seed is data applied through the same DDL the tools use.** A malformed seed row is
   rejected rather than loaded. If `seed()` raises, fix the row, do not bypass the constraint.
4. **`PH1` was an unresolved code** appearing in legacy rows 26 and 40. Resolved 2026-10-06 by the
   operator: PH1 World Developers, Inc., Megawide's real-estate subsidiary (unlisted). The
   resolution came from the operator, not from an agent inferring one — keep that distinction,
   since the point of the seed's `UNRESOLVED` marker was to force the question rather than guess.
5. **The registry says `ICTSI`; Libram says `ICT`.** The mapping lives in `entity.libram_code`.
   Any future resolver must translate, not assume.
6. **`uv run` wants a writable cache at runtime**, so the container entrypoint runs
   `./.venv/bin/fastmcp` instead. Do not "simplify" it back to `uv run`.
7. **`network_mode: host` means a `ports:` mapping is a no-op.** The bound port *is* the host port.
8. **`fastmcp` is pinned to `<4`.** A major bump can move decorator kwargs and CLI subcommands.

## Verification

```sh
uv run pytest
MONITOR_DB=/tmp/x.db ./.venv/bin/fastmcp run main.py:mcp --transport http --port 6776 &
./.venv/bin/fastmcp list http://127.0.0.1:6776/mcp
./.venv/bin/fastmcp call http://127.0.0.1:6776/mcp init
```

There is no Docker daemon inside the Hermes container, so image build and compose startup are
host-side and unverified from here.
