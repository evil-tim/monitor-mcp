# monitor-mcp

A constraint-enforced signal registry for situational awareness over the PSE, Philippine
macro, and the wider economy. It is the **store** half of a trigger watch: it holds what to
monitor, records what was observed, and derives what is overdue. It does not yet resolve
anything automatically, and by design it never guesses.

MCP endpoint (production, host networking): `http://127.0.0.1:7776/mcp`
Development: `http://127.0.0.1:6776/mcp`

## Why a database rather than a markdown table

The registry started as a 40-row markdown table inside the wiki. Markdown cannot **reject** a
write, only display one, so every rule was a convention that failed silently. It showed: the
source file already had two sections numbered `CATEGORY 9`, one row with six cells instead of
seven, and readings five months stale sitting in a document whose frontmatter claimed a recent
update.

Every constraint in `monitor_mcp/migrations/0001_init.sql` exists to make a specific class of
drift *impossible* rather than merely detectable. `docs/plan-v1.md` maps drift mode to
constraint one for one.

## Layout

```
main.py                        entrypoint object for `fastmcp run main.py:mcp`
monitor_mcp/
  config.py                    lazy config; never resolved at import
  models.py                    vocabularies, slot arithmetic, derived-state rules
  store.py                     THE enforcement boundary: all reads and writes
  render.py                    renders the status document as a build artifact
  server.py                    the MCP tool surface
  migrations/0001_init.sql     schema, CHECK constraints, append-only triggers
  seed_signals.py              GENERATED - 40 rows, 12 entities
tools/
  extract_registry.py          regenerates the seed from the wiki source
  EXTRACTION_REPORT.md         provenance and open questions
```

## Running it

```sh
uv sync
uv run pytest                      # the suite asserts every guardrail actually rejects
MONITOR_DB=/tmp/monitor.db PORT=6776 uv run fastmcp run main.py:mcp \
    --transport http --host 127.0.0.1 --port 6776
```

Exercise it without writing client code, since the `fastmcp` CLI is its own MCP client:

```sh
./.venv/bin/fastmcp list http://127.0.0.1:6776/mcp
./.venv/bin/fastmcp call http://127.0.0.1:6776/mcp init
./.venv/bin/fastmcp call http://127.0.0.1:6776/mcp list_due '{"limit": 5}'
```

## Tool surface

| Tool | Purpose |
|---|---|
| `init` | apply migrations and load the seed. Idempotent |
| `status` | health, coverage, and every row's derived state |
| `list_due` | rows needing attention, most urgent first, capped by `limit` |
| `get_signal` | one row in full, with its reading history |
| `record_reading` | record one observation, validated and rejected rather than corrected |
| `mark_unverified` | record that a row could **not** be read, with the reason |
| `add_signal` | add a row |
| `retire_signal` | take a row out of scope (never deleted) |
| `label_signal` | replace a row's free-form labels |
| `render_status` | render the status document |

There is deliberately no raw-SQL tool. One would reintroduce every failure the schema exists
to prevent.

## Registering with Hermes

Config, connectivity and tool availability are three different things. Adding the server to
`mcp_servers:` proves none of them on its own, and **discovery happens per process** at start
and on `/reload-mcp` — so the server must be listening before discovery, and a new session is
needed afterwards. Tool counts log as native + 4, because Hermes adds four generic bridge tools
per server.

```yaml
mcp_servers:
  monitor:
    url: "http://127.0.0.1:7776/mcp"
```

## State

`/opt/data/monitoring/monitor.db` on the host, mounted at `/state` in the container. `/opt/data`
is a real ext4 mount rather than container-layer, so the database survives the host-side image
replacement that `hermes update` requires here.

## Status

v1 is **store and spec only**. Every row is `manual`: no resolvers, no alerting. See
`docs/plan-v1.md` for what that excludes and why.
