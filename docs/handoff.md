# Handoff — monitor-mcp v1

Written 2026-09-24, at commit `971f6f7`. Read this before touching anything.

## Where things stand

The store is built, tested and pushed. Deployment and the wiki migration are **not done** —
they were deliberately deferred to a separate session. Every row is `mode='manual'`: there are
no resolvers and no alerting, by choice, so nothing writes to the store automatically yet.

## What exists

| Artifact | Path | State |
|---|---|---|
| Repo | `github.com/evil-tim/monitor-mcp` | pushed, `971f6f7`, branch `main`, clean |
| Working copy | `/opt/repos/monitor-mcp` | clean, HEAD == remote |
| Schema | `monitor_mcp/migrations/0001_init.sql` | applied as version 1 |
| Seed | `monitor_mcp/seed_signals.py` | **generated** — 40 rows, 12 entities |
| Design record | `docs/plan-v1.md` | locked |
| Provenance | `tools/EXTRACTION_REPORT.md` | 13 flagged rows, 6 open questions |
| Test suite | `tests/` | 64 tests |
| Live database | *none yet* | deploy step creates it |

## Verified vs unverified

This distinction matters more than the feature list.

| Claim | Status |
|---|---|
| 64 tests pass | **verified** |
| Server starts and answers HTTP on 6776 | **verified** |
| 10 tools discovered by the `fastmcp` client | **verified** |
| `init` applies migration 1 and seeds 40 rows + 12 entities | **verified** |
| Weekly slot derives to Monday (`2026-09-21`) | **verified** |
| Duplicate-slot write rejected | **verified** |
| In-code validation rejections fire (attribution, missing value) | **verified** |
| `mark_unverified` records a first-class outcome | **verified** |
| `render_status` output verifies against its own hash | **verified** |
| Docker image builds | **NOT verified** — no daemon in the Hermes container |
| Compose starts the service | **NOT verified** — same |
| Hermes discovers the tools in a live session | **NOT verified** — registration not done |
| Any row actually read against its named source | **NOT done** — all 40 are `NEVER_READ` |

## Deployment (host-side, because this container has no Docker daemon)

### 1. Create the state directory, owner 1000

```sh
sudo mkdir -p /opt/data/monitoring
sudo chown 1000:1000 /opt/data/monitoring
```

**Do not skip the `chown`.** Docker creates a missing bind-mount host directory as `root:root`,
and the container runs as uid 1000 (`user: 1000:1000`), so the server would fail to create the
database with a permission error that looks like a code fault. This is the single most likely
way the first deploy goes wrong.

### 2. Build and start

```sh
cd /opt/repos/monitor-mcp
docker compose build
docker compose up -d
docker compose logs -f monitor-mcp
```

The entrypoint runs `./.venv/bin/fastmcp` rather than `uv run`, deliberately: `uv run` wants a
writable cache at runtime, which forecloses a read-only root filesystem later. Do not
"simplify" it back.

### 3. Verify the deployed container

```sh
# readiness: poll the socket rather than sleeping blind
python3 -c "import socket;s=socket.socket();s.settimeout(0.3);print(s.connect_ex(('127.0.0.1',7776))==0)"

python3 tools/../scripts_probe.py 2>/dev/null || true
./.venv/bin/fastmcp list http://127.0.0.1:7776/mcp
./.venv/bin/fastmcp call http://127.0.0.1:7776/mcp status
```

Expect: 10 tools, `schema_version` 1, 40 signals, 12 entities, `never_read` 40.

`network_mode: host` means the container's bound port *is* the host port — a `ports:` mapping
would be a no-op, and is deliberately absent.

### 4. Register with Hermes

Config, connectivity and tool availability are three different things, and **discovery is per
process** — Hermes connects and calls `list_tools()` at process start and on `/reload-mcp`, never
automatically mid-process.

```yaml
mcp_servers:
  monitor:
    url: "http://127.0.0.1:7776/mcp"
```

Then:

1. Confirm the server is listening **before** the gateway starts, or expect
   `legacy handshake rejected (Not Found)` followed by a park; it recovers on the next reload,
   not by itself.
2. `/reload-mcp`, then start a **new session** (`/new`). Tool changes never apply mid-conversation.
3. Expect the log to read `registered N tool(s)` where N is our 10 plus 4 generic bridge tools
   Hermes adds per server. That arithmetic is not a bug.

Three probes settle any doubt, one call each: the `fastmcp` client (what the server exposes),
`$HERMES_HOME/logs/agent.log` lines `MCP server 'monitor' (HTTP): registered` (what each process
discovered), and `$HERMES_HOME/cache/mcp_schema_cache.json` (last-discovered schema per server).

Setting the env without restarting proves nothing.

## The migration task

Two things move, and they are different sizes.

### A. The registry is already migrated

The 40 rows left markdown when they entered the seed. `queries/future-events-monitoring-dashboard-2026.md`
now has no job: it is a duplicate representation of the same instrument. Decide its fate — the
cleanest is to replace its body with a generated render of `render_status()` so the path keeps
working for anything that linked to it, and the document becomes a build artifact.

### B. The framework file still needs migrating

`queries/future-events-monitoring-framework-2026.md` — **1,513 lines, 109 KB, 16 inbound links**,
9 category sections, and *two* sections numbered `CATEGORY 9` (banking at 935, BPO at 1276).

The approved approach: migrate its per-category prose into the entity and concept pages that
already carry each thesis, then archive the shell.

- Do it as its own pass. 16 inbound links means a careless move breaks navigation across the wiki.
- The entity pages already hold the analysis: `entities/acen.md`, `entities/megawide.md`,
  `entities/rcr.md`, `entities/meralco.md` and friends. Most of the framework's prose is a
  restatement of what those pages argue, which is why it duplicated the dashboard in the first place.
- Archive with the wiki's own convention (`_archive/`, remove from the index, update inbound
  links to plain text plus "(archived)"), then log the action.
- `llm-wiki` governs this work; run `wikilint` before and after and compare the broken-link count
  as a **delta**, not an absolute. A large standing baseline is expected.

### C. Entity pages gain a monitoring link

Give each entity page a frontmatter list of the signal slugs that concern it, so impacts point one
way (page → registry) rather than being duplicated as prose in both. The slugs are stable; the
`entity.libram_code` column already records the one known mismatch (`ICTSI` vs Libram's `ICT`).

## Open questions carried forward

1. **`PH1` is unresolved.** Used as an entity in legacy rows 26 and 40 but not a recognisable code.
   Seeded as `UNRESOLVED ... meaning not established`. Do not invent a company for it — ask.
2. **`ICTSI` vs `ICT`.** The registry's code and Libram's differ. Recorded in `entity.libram_code`.
3. **`NGCP` is not PSE-listed** but the registry treats it as an entity. Kept, `feed='manual'`.
4. **`review_by` on the 10 qualitative rows is a placeholder** (today + 180 days), not an operator
   decision. It needs a real answer before it starts firing `DUE_REVIEW`.
5. **"Compound" was mis-extracted as a tier.** Legacy row 1 returns four tiers:
   `Alert <172`, `Critical <170`, `Emergency <165`, `Compound <172`. The first three are real; the
   fourth is a compound *condition*, matched as a tier by the extractor's regex. Harmless while
   tiers are unenforced, but fix before anything reads them.
6. **`signal_compound` is empty.** Compound conditions survive as prose. Rows 1, 3 and 7 are known
   candidates; the Angat row's real condition is `<172 m AND PASA Strong El Niño AND NGCP reserve
   margin <12%`, which is three rows ANDed.
7. **Legacy row 28 has 6 cells where every other row has 7** — its impacts live inside the
   threshold cell. The legacy table was already internally inconsistent.

## Gotchas worth preserving

- **The migration runner owns `schema_version`.** It must exist before any migration runs, so no
  migration file may create it. Getting this wrong passes on a migrated database and dies on a
  fresh one with `table schema_version already exists` — which is exactly what happened.
- **`uv sync` fails while pyproject declares an unwritten `README.md`.** Write the README first.
- **A validator that silently no-ops is worse than no validator.** The CSV prototype had a str/int
  key mismatch that disabled a check invisibly, caught only by reading output showing three defects
  where four were expected. Hence `tests/test_guardrails.py`: every rule is tested by attempting
  the violation and asserting the rejection.
- **`fastmcp` is pinned `<4`.** A major bump can move decorator kwargs and CLI subcommands.
- **`pkill -f <pattern>` matches its own command line.** Use `pkill -f '[f]astmcp'`.
- **Test migrations against a fresh temporary database**, never the dev one — a dev database hides
  exactly the bug above.

## Environment facts

- No Docker daemon inside the Hermes container; builds and compose are host-side.
- `/opt/data` is a real ext4 mount (`/dev/nvme0n1p5`), not container-layer, so the database
  survives the host-side image replacement that `hermes update` requires here.
- Timezone is `Asia/Manila`; the Philippines has no DST so the fixed `+08:00` offset in
  `config.MANILA` is exact rather than an approximation.
- `HOME` is `/opt/data/home`, not `/opt/data`.
