"""Controlled vocabularies, cadence windows, and derived-state arithmetic.

The vocabularies mirror the CHECK constraints in migrations/0001_init.sql exactly. If they
drift from the DDL the database rejects writes - which is the intended failure mode, and why
tests/test_guardrails.py asserts that each constraint actually fires.
"""
from __future__ import annotations

import datetime as dt

CATEGORIES = ("Grid", "Market", "Political", "Supply", "Financial",
              "Infra", "Execution", "Macro", "Labor")
CADENCES = ("daily", "weekly", "monthly", "quarterly", "event")
KINDS = ("threshold", "event", "qualitative")
MODES = ("manual", "dry-run", "auto", "retired")
STATUSES = ("OK", "TRIGGERED", "UNVERIFIED", "STALE", "DUE", "RETIRED")
METHODS = ("libram", "api", "fetch", "manual")
CONFIDENCES = ("primary", "secondary", "proxy")
OPS = (">=", "<=", ">", "<", "==")
FEEDS = ("libram", "web", "manual")

CADENCE_DAYS = {"daily": 1, "weekly": 7, "monthly": 31, "quarterly": 92, "event": 3650}

# Derived states. Computed at query time and never stored on the spec row, because a stored
# status is a second source of truth that drifts from the readings it was derived from.
NEVER_READ = "NEVER_READ"
CURRENT = "CURRENT"
STALE = "STALE"
TRIGGERED = "TRIGGERED"
DUE_SOON = "DUE_SOON"
DUE_EVENT = "DUE_EVENT"
DUE_REVIEW = "DUE_REVIEW"
RETIRED = "RETIRED"

DERIVED_STATES = (NEVER_READ, CURRENT, STALE, TRIGGERED, DUE_SOON, DUE_EVENT, DUE_REVIEW, RETIRED)
NEEDS_ATTENTION = (NEVER_READ, STALE, TRIGGERED, DUE_SOON, DUE_EVENT, DUE_REVIEW)

STATE_MEANING = {
    NEVER_READ: "the row exists but has never been read",
    CURRENT: "read within its own cadence window",
    STALE: "not read within its cadence window",
    TRIGGERED: "the newest reading met the row's threshold",
    DUE_SOON: "a dated event is approaching",
    DUE_EVENT: "a dated event has passed with no outcome recorded",
    DUE_REVIEW: "a qualitative row has passed its review_by date",
    RETIRED: "out of scope",
}


def window_days(cadence: str) -> int:
    try:
        return CADENCE_DAYS[cadence]
    except KeyError:
        raise ValueError(f"unknown cadence {cadence!r}; expected one of {CADENCES}") from None


def slot_for(cadence: str, when: dt.datetime) -> str:
    """The logical slot for a cadence, derived from the calendar rather than from now().

    Deterministic on purpose: a retry then collapses onto the same slot and the
    UNIQUE(signal_id, slot) constraint rejects the duplicate instead of quietly inventing a
    second reading for the same period.
    """
    d = when.date()
    if cadence == "weekly":
        d = d - dt.timedelta(days=d.weekday())
    elif cadence == "monthly":
        d = d.replace(day=1)
    elif cadence == "quarterly":
        d = d.replace(month=3 * ((d.month - 1) // 3) + 1, day=1)
    return f"{d.isoformat()}T00:00:00+08:00"


def parse_slot(slot: str) -> dt.datetime:
    return dt.datetime.fromisoformat(slot)


def derive_state(*, mode: str, cadence: str, kind: str, due_date: str | None,
                 review_by: str | None, last_slot: str | None, last_status: str | None,
                 now: dt.datetime, due_horizon_days: int = 30) -> str:
    """Derive a row's state from its cadence and its newest reading.

    Precedence is deliberate: RETIRED beats everything (out of scope), then NEVER_READ
    (nothing to reason about), then TRIGGERED (an alert outranks a staleness complaint),
    then the kind-specific date rules, then cadence staleness.
    """
    if mode == "retired":
        return RETIRED
    if last_slot is None:
        return NEVER_READ
    if last_status == "TRIGGERED":
        return TRIGGERED

    last = parse_slot(last_slot)
    today = now.date()

    if kind == "event" and due_date:
        due = dt.date.fromisoformat(due_date)
        if today >= due and last.date() < due:
            return DUE_EVENT
        if 0 <= (due - today).days <= due_horizon_days:
            return DUE_SOON

    if kind == "qualitative" and review_by:
        if today >= dt.date.fromisoformat(review_by):
            return DUE_REVIEW

    age = (now - last).total_seconds() / 86400.0
    if age > window_days(cadence):
        return STALE
    return CURRENT


def overdue_days(*, cadence: str, last_slot: str | None, now: dt.datetime) -> float | None:
    """How far past its cadence window a row is. None when it has never been read."""
    if last_slot is None:
        return None
    age = (now - parse_slot(last_slot)).total_seconds() / 86400.0
    return round(age - window_days(cadence), 1)


def compare(value: float, op: str, threshold: float) -> bool:
    return {">=": value >= threshold, "<=": value <= threshold,
            ">": value > threshold, "<": value < threshold,
            "==": value == threshold}[op]
