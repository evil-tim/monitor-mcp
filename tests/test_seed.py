from monitor_mcp import models, seed_signals, store


def test_seed_shape():
    assert len(seed_signals.SIGNALS) == 41
    assert len(seed_signals.ENTITIES) == 12


def test_legacy_rows_are_complete_and_unique(con):
    got = sorted(r[0] for r in con.execute("SELECT legacy_row FROM signal") if r[0] is not None)
    assert got == list(range(1, 41))       # every dashboard row is present exactly once
    # rows added after the migration carry no legacy_row: they are not dashboard rows
    n_null = con.execute("SELECT COUNT(*) FROM signal WHERE legacy_row IS NULL").fetchone()[0]
    assert n_null == len(seed_signals.SIGNALS) - 40


def test_kind_distribution(con):
    kinds = dict(con.execute("SELECT kind, COUNT(*) FROM signal GROUP BY kind"))
    assert kinds == {"threshold": 30, "event": 1, "qualitative": 10}


def test_every_row_satisfies_its_own_kind_constraint(con):
    # implied by a successful insert, but asserted explicitly because it is the contract
    for r in con.execute("SELECT slug, kind, op, threshold_num, due_date, review_by FROM signal"):
        slug, kind, op, thr, due, rev = r
        if kind == "threshold":
            assert op is not None and thr is not None, slug
        elif kind == "event":
            assert due is not None, slug
        else:
            assert rev is not None, slug


def test_impacts_reference_real_entities(con):
    orphans = list(con.execute(
        """SELECT i.ticker FROM signal_impact i
           LEFT JOIN entity e ON e.ticker = i.ticker WHERE e.ticker IS NULL"""))
    assert orphans == []


def test_libram_code_mapping_is_recorded(con):
    row = con.execute("SELECT libram_code FROM entity WHERE ticker='ICTSI'").fetchone()
    assert row[0] == "ICT"      # the registry says ICTSI; Libram says ICT


def test_seed_is_idempotent(con):
    before = (con.execute("SELECT COUNT(*) FROM signal").fetchone()[0],
              con.execute("SELECT COUNT(*) FROM reading").fetchone()[0],
              con.execute("SELECT COUNT(*) FROM signal_tier").fetchone()[0])
    store.seed(con)
    store.seed(con)
    after = (con.execute("SELECT COUNT(*) FROM signal").fetchone()[0],
             con.execute("SELECT COUNT(*) FROM reading").fetchone()[0],
             con.execute("SELECT COUNT(*) FROM signal_tier").fetchone()[0])
    assert before == after


def test_status_reports_coverage(con):
    s = store.status(con)
    assert s["signals"] == 41
    assert s["entities"] == 12
    assert s["readings"] == 0
    assert s["never_read"] == 41
    assert s["by_kind"] == {"threshold": 30, "event": 1, "qualitative": 10}
    assert s["by_cadence"]["daily"] == 2
    assert s["schema_version"] == 1


def test_tiers_survive_the_seed(con):
    n = con.execute("SELECT COUNT(*) FROM signal_tier").fetchone()[0]
    assert n > 0, "tiered rows should have carried their tiers across"


def test_labels_are_free_form(con):
    r = store.label_signal(con, "php-usd-spot-rate-trend",
                           ["rate-sensitive", "fx-exposed", "2026-watch"], kind="risk")
    assert r.get("ok") is True
    sig = store.get_signal(con, "php-usd-spot-rate-trend")
    assert sig["labels"] == ["2026-watch", "fx-exposed", "rate-sensitive"]
    # relabelling replaces, and cannot desynchronise anything
    store.label_signal(con, "php-usd-spot-rate-trend", ["fx-exposed"])
    assert store.get_signal(con, "php-usd-spot-rate-trend")["labels"] == ["fx-exposed"]


def test_ph1_is_the_resolved_real_estate_entity(con):
    row = con.execute("SELECT name, libram_code FROM entity WHERE ticker='PH1'").fetchone()
    assert "PH1 World Developers" in row["name"]
    assert row["libram_code"] is None      # not PSE-listed


def test_tool_added_row_carries_its_impacts_and_tiers(con):
    # the row added by hand must load its child tables through the same seed path
    sig = store.get_signal(con, "philippines-headline-inflation")
    assert sig is not None
    assert {i["ticker"]: i["direction"] for i in sig["impacts"]} == {
        "BPI": "down", "ACEN": "down", "CREC": "down", "CREIT": "down",
        "MWIDE": "down", "ICTSI": "down", "SCC": "up"}
    assert [(t["label"], t["op"], t["threshold_num"]) for t in sig["tiers"]] == [
        ("Alert", ">", 4.0), ("Stress", ">", 6.0), ("Critical", ">", 7.0)]
    # SCC is up here, deliberately unlike row 27's financial-conditions read
    scc = next(i for i in sig["impacts"] if i["ticker"] == "SCC")
    assert scc["direction"] == "up"
