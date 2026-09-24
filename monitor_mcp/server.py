"""The MCP tool surface.

Deliberately small, because every registered server's tool schemas are loaded into every
session that has it configured. Intention-shaped tools only: there is no raw-SQL tool,
because one would reintroduce every failure the DDL exists to prevent.

Every tool opens its own connection and closes it, so configuration is resolved per call
rather than at import. That keeps the process startable with the database missing, which is
what lets `status` explain the problem instead of dying with a traceback.
"""
from __future__ import annotations

import datetime as dt

from fastmcp import FastMCP

from . import config, render, store

mcp = FastMCP(
    name="MONITOR-MCP",
    instructions=(
        "Constraint-enforced signal registry for PSE and macro monitoring. Rows are monitoring "
        "signals with a permanent slug and a cadence; readings are append-only observations "
        "carrying provenance. Every write is validated and rejected rather than corrected. When "
        "a row cannot be read, record that honestly with mark_unverified: an instrument that "
        "cannot distinguish 'nothing changed' from 'I could not look' is lying to its reader."
    ),
)


def _con():
    return store.connect()


def _not_initialised(con) -> dict | None:
    if store.initialised(con):
        return None
    return {"error": "schema not initialised",
            "hint": "call init() to apply migrations and load the seed registry",
            "db_path": str(config.db_path())}


def _now() -> dt.datetime:
    return dt.datetime.now(config.MANILA)


@mcp.tool(name="init",
          description="Apply pending migrations and load the seed registry. Idempotent: "
                      "re-running updates the spec and never deletes readings.")
def init() -> dict:
    con = _con()
    try:
        applied = store.migrate(con)
        seeded = store.seed(con)
        return {"ok": True, "migrations_applied": applied, "seeded": seeded,
                "db_path": str(config.db_path()),
                "schema_version": store.schema_version(con)}
    finally:
        con.close()


@mcp.tool(name="status",
          description="Health and coverage: database path, schema version, counts by kind, "
                      "cadence and derived state, plus every row's current state.")
def status() -> dict:
    con = _con()
    try:
        return store.status(con, now=_now())
    finally:
        con.close()


@mcp.tool(name="list_due",
          description="Rows needing attention, most urgent first. Never-read rows rank above "
                      "merely stale ones, because unknown outranks late. Use the limit to stay "
                      "inside a bounded run: process these, let the rest roll to the next tick.")
def list_due(limit: int = 10) -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        rows = store.list_due(con, limit=max(1, limit), now=_now())
        keys = ("slug", "legacy_row", "category", "kind", "cadence", "state",
                "overdue_days", "last_slot", "value_num", "description", "source")
        return {"count": len(rows), "limit": limit,
                "rows": [{k: r[k] for k in keys} for r in rows]}
    finally:
        con.close()


@mcp.tool(name="get_signal",
          description="One row in full: spec, tiers, impacted entities, labels, derived state "
                      "and its reading history newest first.")
def get_signal(slug: str, readings: int = 20) -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        sig = store.get_signal(con, slug, readings=max(1, readings), now=_now())
        return sig or {"error": f"unknown signal slug: {slug!r}",
                       "hint": "list_due() and status() list the slugs that exist"}
    finally:
        con.close()


@mcp.tool(name="record_reading",
          description="Record one observation. Validated and rejected, never corrected. The slot "
                      "is derived from the row's cadence, so re-recording the same period is "
                      "rejected as a duplicate instead of creating a second reading. Primary "
                      "confidence requires a source_url or method='libram'.")
def record_reading(slug: str, status: str = "OK", method: str = "manual",
                   confidence: str = "primary", value_num: float | None = None,
                   raw_text: str | None = None, source_url: str | None = None,
                   note: str | None = None) -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        return store.record_reading(
            con, slug, status=status, method=method, confidence=confidence,
            value_num=value_num, raw_text=raw_text, source_url=source_url, note=note,
            when=_now())
    finally:
        con.close()


@mcp.tool(name="mark_unverified",
          description="Record that a row could NOT be read, with the reason. A first-class "
                      "outcome, not a failure. Prefer it over guessing: a row reporting "
                      "UNVERIFIED is useful, a row reporting a plausible invention is worse "
                      "than nothing.")
def mark_unverified(slug: str, reason: str, method: str = "manual",
                    source_url: str | None = None, confidence: str = "secondary") -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        return store.mark_unverified(con, slug, reason, method=method,
                                     source_url=source_url, confidence=confidence, when=_now())
    finally:
        con.close()


@mcp.tool(name="add_signal",
          description="Add a monitoring row. kind='threshold' needs op and threshold_num; "
                      "kind='event' needs due_date; kind='qualitative' needs review_by, because "
                      "a row with no checkable property is not monitorable.")
def add_signal(slug: str, category: str, description: str, source: str, cadence: str,
               kind: str, op: str | None = None, threshold_num: float | None = None,
               due_date: str | None = None, review_by: str | None = None,
               legacy_row: int | None = None, rationale: str | None = None,
               mode: str = "manual") -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        return store.add_signal(con, slug, category=category, description=description,
                                source=source, cadence=cadence, kind=kind, op=op,
                                threshold_num=threshold_num, due_date=due_date,
                                review_by=review_by, legacy_row=legacy_row,
                                rationale=rationale, mode=mode)
    finally:
        con.close()


@mcp.tool(name="retire_signal",
          description="Take a row out of scope. Rows are retired, never deleted: readings "
                      "already recorded stay, and the row stops appearing in list_due.")
def retire_signal(slug: str, reason: str) -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        return store.retire_signal(con, slug, reason)
    finally:
        con.close()


@mcp.tool(name="label_signal",
          description="Replace a row's free-form labels (regrouping, portfolio sleeves, risk "
                      "themes). Labels are data rather than structure, so regrouping can never "
                      "desynchronise anything.")
def label_signal(slug: str, labels: list[str], kind: str = "tag") -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        return store.label_signal(con, slug, labels, kind=kind)
    finally:
        con.close()


@mcp.tool(name="render_status",
          description="Render the status document from the store. Generated, hash-stamped and "
                      "safe to overwrite: the document is a build artifact, so it can never "
                      "accumulate drift.")
def render_status() -> dict:
    con = _con()
    try:
        bad = _not_initialised(con)
        if bad:
            return bad
        payload = store.status(con, now=_now())
        doc = render.render_status(payload)
        return {"markdown": doc, "verified": render.verify(doc),
                "bytes": len(doc.encode("utf-8"))}
    finally:
        con.close()


def main() -> None:
    """Run over HTTP, matching the fleet's 777x production port convention."""
    mcp.run(transport="http", host="0.0.0.0", port=config.port())


if __name__ == "__main__":
    main()
