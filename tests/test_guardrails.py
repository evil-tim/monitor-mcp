"""Every guardrail asserted to actually REJECT something.

A validator that silently no-ops is worse than no validator, because it manufactures
confidence. So each rule below is tested by attempting the violation and asserting the
rejection, not by inspecting the schema and assuming it works.
"""
import sqlite3

import pytest

from monitor_mcp import store


def mk_signal(con, slug="sig-a", **over):
    vals = dict(slug=slug, category="Macro", description="d", source="s", cadence="weekly",
                kind="threshold", op=">=", threshold_num=1.0, due_date=None, review_by=None,
                mode="manual", legacy_row=None)
    vals.update(over)
    con.execute(
        """INSERT INTO signal(slug, category, description, source, cadence, kind, op,
                              threshold_num, due_date, review_by, mode, legacy_row,
                              created_at, updated_at)
           VALUES(:slug,:category,:description,:source,:cadence,:kind,:op,:threshold_num,
                  :due_date,:review_by,:mode,:legacy_row,'t','t')""", vals)
    return con.execute("SELECT id FROM signal WHERE slug=?", (vals["slug"],)).fetchone()[0]


def mk_reading(con, sid, slot="2026-01-05T00:00:00+08:00", **over):
    vals = dict(signal_id=sid, slot=slot, checked_at="2026-01-05T09:00:00+08:00",
                value_num=1.0, raw_text=None, status="OK", method="manual",
                confidence="secondary", source_url=None, note=None)
    vals.update(over)
    con.execute(
        """INSERT INTO reading(signal_id, slot, checked_at, value_num, raw_text, status,
                               method, confidence, source_url, note)
           VALUES(:signal_id,:slot,:checked_at,:value_num,:raw_text,:status,:method,
                  :confidence,:source_url,:note)""", vals)


# ---------------------------------------------------------------- schema guardrails
def test_rejects_unknown_op(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", op="~=")


def test_rejects_threshold_kind_without_predicate(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", op=None, threshold_num=None)


def test_rejects_event_kind_without_due_date(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", kind="event", op=None, threshold_num=None)


def test_rejects_qualitative_kind_without_review_by(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", kind="qualitative", op=None, threshold_num=None)


def test_rejects_unknown_category(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", category="Vibes")


def test_rejects_unknown_cadence(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", cadence="hourly")


def test_rejects_unknown_kind(bare):
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", kind="sentiment")


def test_rejects_auto_mode_without_predicate(bare):
    # nothing may claim to be machine-resolvable without a machine-comparable predicate
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="x", kind="qualitative", op=None, threshold_num=None,
                  review_by="2027-01-01", mode="auto")


def test_rejects_duplicate_slug(bare):
    mk_signal(bare, slug="dup")
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="dup")


def test_rejects_duplicate_legacy_row(bare):
    mk_signal(bare, slug="a", legacy_row=7)
    with pytest.raises(sqlite3.IntegrityError):
        mk_signal(bare, slug="b", legacy_row=7)


def test_rejects_impact_on_unknown_ticker(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("INSERT INTO signal_impact VALUES(?,?,?)", (sid, "NOSUCH", "down"))


def test_rejects_unknown_impact_direction(bare):
    bare.execute("INSERT INTO entity VALUES('X','X','manual',NULL)")
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("INSERT INTO signal_impact VALUES(?,?,?)", (sid, "X", "sideways"))


def test_rejects_compound_self_reference(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("INSERT INTO signal_compound VALUES(?,?)", (sid, sid))


def test_rejects_reading_without_confidence(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute(
            """INSERT INTO reading(signal_id, slot, checked_at, status, method, confidence)
               VALUES(?, '2026-01-05T00:00:00+08:00','t','OK','manual',NULL)""", (sid,))


def test_rejects_unknown_reading_status(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        mk_reading(bare, sid, status="PROBABLY_FINE")


def test_rejects_unknown_method(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        mk_reading(bare, sid, method="vibes")


def test_rejects_duplicate_slot(bare):
    sid = mk_signal(bare, slug="a")
    mk_reading(bare, sid)
    with pytest.raises(sqlite3.IntegrityError):
        mk_reading(bare, sid)          # same logical slot, second write


# ---------------------------------------------------------------- append-only triggers
def test_rejects_reading_update(bare):
    sid = mk_signal(bare, slug="a")
    mk_reading(bare, sid)
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("UPDATE reading SET value_num=99 WHERE signal_id=?", (sid,))


def test_rejects_reading_delete(bare):
    sid = mk_signal(bare, slug="a")
    mk_reading(bare, sid)
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("DELETE FROM reading WHERE signal_id=?", (sid,))


def test_rejects_signal_delete(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("DELETE FROM signal WHERE id=?", (sid,))


def test_rejects_slug_rename(bare):
    sid = mk_signal(bare, slug="a")
    with pytest.raises(sqlite3.IntegrityError):
        bare.execute("UPDATE signal SET slug='renamed' WHERE id=?", (sid,))


# ---------------------------------------------------------------- in-code validation
def test_unverified_requires_a_reason(con):
    r = store.record_reading(con, "angat-dam-water-level", status="UNVERIFIED")
    assert "error" in r
    assert any("requires a note" in x for x in r["reasons"])


def test_unverified_cannot_be_primary_confidence(con):
    # you cannot be certain about not having read something
    r = store.record_reading(con, "angat-dam-water-level", status="UNVERIFIED",
                             note="telemetry page 502", confidence="primary")
    assert "error" in r
    assert any("primary confidence" in x for x in r["reasons"])


def test_threshold_row_requires_a_value(con):
    r = store.record_reading(con, "angat-dam-water-level", status="OK", value_num=None)
    assert "error" in r
    assert any("requires value_num" in x for x in r["reasons"])


def test_primary_confidence_requires_attribution(con):
    r = store.record_reading(con, "angat-dam-water-level", value_num=174.5,
                             method="manual", confidence="primary", source_url=None)
    assert "error" in r
    assert any("attributable source" in x for x in r["reasons"])


def test_libram_method_is_attribution_enough(con):
    r = store.record_reading(con, "php-usd-spot-rate-trend", value_num=4.8,
                             method="libram", confidence="primary")
    assert r.get("ok") is True


def test_retired_row_rejects_further_writes(con):
    store.retire_signal(con, "angat-dam-water-level", "superseded")
    r = store.record_reading(con, "angat-dam-water-level", value_num=1.0,
                             confidence="secondary")
    assert "error" in r
    assert any("retired" in x for x in r["reasons"])


def test_unknown_slug_is_rejected(con):
    r = store.record_reading(con, "no-such-slug", value_num=1.0, confidence="secondary")
    assert "error" in r


def test_mark_unverified_is_a_first_class_outcome(con):
    r = store.mark_unverified(con, "angat-dam-water-level", "NPC telemetry returned 502")
    assert r.get("ok") is True
    sig = store.get_signal(con, "angat-dam-water-level")
    assert sig["readings"][0]["status"] == "UNVERIFIED"
    assert sig["readings"][0]["note"] == "NPC telemetry returned 502"
