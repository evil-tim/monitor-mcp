import datetime as dt

import pytest

from monitor_mcp import config, models, store

NOW = dt.datetime(2026, 9, 24, 18, 0, tzinfo=config.MANILA)   # a Thursday


def test_slot_for_is_calendar_aligned():
    assert models.slot_for("daily", NOW) == "2026-09-24T00:00:00+08:00"
    assert models.slot_for("weekly", NOW) == "2026-09-21T00:00:00+08:00"      # Monday
    assert models.slot_for("monthly", NOW) == "2026-09-01T00:00:00+08:00"
    assert models.slot_for("quarterly", NOW) == "2026-07-01T00:00:00+08:00"


def test_slot_for_is_deterministic_within_a_period():
    # the whole point: a retry lands on the same slot, so UNIQUE rejects the duplicate
    a = models.slot_for("weekly", dt.datetime(2026, 9, 21, 9, 0, tzinfo=config.MANILA))
    b = models.slot_for("weekly", dt.datetime(2026, 9, 27, 23, 0, tzinfo=config.MANILA))
    assert a == b


@pytest.mark.parametrize("kwargs,expected", [
    (dict(mode="retired", cadence="weekly", kind="threshold", due_date=None, review_by=None,
          last_slot="2026-09-21T00:00:00+08:00", last_status="OK"), models.RETIRED),
    (dict(mode="manual", cadence="weekly", kind="threshold", due_date=None, review_by=None,
          last_slot=None, last_status=None), models.NEVER_READ),
    (dict(mode="manual", cadence="weekly", kind="threshold", due_date=None, review_by=None,
          last_slot="2026-01-05T00:00:00+08:00", last_status="TRIGGERED"), models.TRIGGERED),
    (dict(mode="manual", cadence="weekly", kind="threshold", due_date=None, review_by=None,
          last_slot="2026-09-21T00:00:00+08:00", last_status="OK"), models.CURRENT),
    (dict(mode="manual", cadence="weekly", kind="threshold", due_date=None, review_by=None,
          last_slot="2026-06-01T00:00:00+08:00", last_status="OK"), models.STALE),
    (dict(mode="manual", cadence="event", kind="event", due_date="2026-09-01",
          review_by=None, last_slot="2026-08-01T00:00:00+08:00", last_status="OK"),
     models.DUE_EVENT),
    (dict(mode="manual", cadence="event", kind="event", due_date="2026-10-05",
          review_by=None, last_slot="2026-09-01T00:00:00+08:00", last_status="OK"),
     models.DUE_SOON),
    (dict(mode="manual", cadence="quarterly", kind="qualitative", due_date=None,
          review_by="2026-09-01", last_slot="2026-06-01T00:00:00+08:00",
          last_status="OK"), models.DUE_REVIEW),
])
def test_derive_state(kwargs, expected):
    assert models.derive_state(now=NOW, **kwargs) == expected


def test_triggered_outranks_stale():
    # an alert must not be hidden by a staleness complaint
    assert models.derive_state(mode="manual", cadence="weekly", kind="threshold",
                               due_date=None, review_by=None,
                               last_slot="2026-01-01T00:00:00+08:00",
                               last_status="TRIGGERED", now=NOW) == models.TRIGGERED


def test_overdue_days():
    assert models.overdue_days(cadence="weekly", last_slot=None, now=NOW) is None
    got = models.overdue_days(cadence="weekly", last_slot="2026-09-14T00:00:00+08:00", now=NOW)
    assert got == pytest.approx(3.75, abs=0.1)


def test_seeded_rows_start_never_read(con):
    rows = store.all_rows(con, now=NOW)
    assert len(rows) == 40
    assert {r["state"] for r in rows} == {models.NEVER_READ}


def test_list_due_ranks_never_read_first_and_respects_limit(con):
    rows = store.list_due(con, limit=5, now=NOW)
    assert len(rows) == 5
    assert all(r["state"] == models.NEVER_READ for r in rows)


def test_recording_moves_a_row_out_of_never_read(con):
    r = store.record_reading(con, "angat-dam-water-level", value_num=174.5,
                             method="manual", confidence="secondary",
                             source_url="https://www.mwss.gov.ph", when=NOW)
    assert r.get("ok") is True
    assert store.state_of(con, "angat-dam-water-level", now=NOW) == models.CURRENT
    # and it drops out of the due list
    due = {x["slug"] for x in store.list_due(con, limit=50, now=NOW)}
    assert "angat-dam-water-level" not in due


def test_stale_row_reappears_as_due(con):
    store.record_reading(con, "angat-dam-water-level", value_num=174.5,
                         confidence="secondary", source_url="https://x", when=NOW)
    later = NOW + dt.timedelta(days=4)      # past the daily window
    assert store.state_of(con, "angat-dam-water-level", now=later) == models.STALE
    due = {x["slug"] for x in store.list_due(con, limit=50, now=later)}
    assert "angat-dam-water-level" in due
