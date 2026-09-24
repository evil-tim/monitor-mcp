"""Configuration, resolved lazily inside each call.

Never resolve at import: the process must be able to start with configuration missing so
that the status tool can explain what is wrong, rather than dying with a stack trace.
"""
from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DB = "/opt/data/monitoring/monitor.db"


def db_path() -> Path:
    return Path(os.environ.get("MONITOR_DB") or DEFAULT_DB)


def tz_name() -> str:
    return os.environ.get("MONITOR_TZ") or "Asia/Manila"


def due_horizon_days() -> int:
    """An event row enters DUE this many days before its date."""
    return int(os.environ.get("MONITOR_DUE_HORIZON_DAYS") or 30)


# Philippines has no DST, so a fixed offset is exact rather than an approximation.
MANILA = __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def port() -> int:
    return int(os.environ.get("PORT") or 7776)
