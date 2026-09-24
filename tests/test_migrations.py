from monitor_mcp import store


def test_expected_objects_exist(bare):
    names = {r[0] for r in bare.execute("SELECT name FROM sqlite_master")}
    for t in ("schema_version", "entity", "signal", "signal_tier", "signal_compound",
              "signal_impact", "label", "signal_label", "reading"):
        assert t in names, f"missing table {t}"
    assert "v_latest_reading" in names


def test_triggers_exist(bare):
    triggers = {r[0] for r in bare.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger'")}
    assert triggers == {"reading_no_update", "reading_no_delete",
                        "signal_no_delete", "signal_slug_immutable"}


def test_version_recorded(bare):
    assert store.schema_version(bare) == 1
    assert store.initialised(bare)


def test_migrate_is_idempotent(bare):
    # a second run must apply nothing: re-running migrations must never re-create objects
    assert store.migrate(bare) == []
    assert store.schema_version(bare) == 1


def test_foreign_keys_enforced(bare):
    assert bare.execute("PRAGMA foreign_keys").fetchone()[0] == 1
