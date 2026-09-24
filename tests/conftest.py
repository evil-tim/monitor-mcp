import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from monitor_mcp import store  # noqa: E402


@pytest.fixture
def con(tmp_path, monkeypatch):
    """Migrated and seeded."""
    monkeypatch.setenv("MONITOR_DB", str(tmp_path / "monitor.db"))
    c = store.connect()
    store.migrate(c)
    store.seed(c)
    try:
        yield c
    finally:
        c.close()


@pytest.fixture
def bare(tmp_path, monkeypatch):
    """Migrated but unseeded, for raw DDL guardrail tests."""
    monkeypatch.setenv("MONITOR_DB", str(tmp_path / "bare.db"))
    c = store.connect()
    store.migrate(c)
    try:
        yield c
    finally:
        c.close()
