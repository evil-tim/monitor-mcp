from monitor_mcp import models, render, store


def test_render_carries_a_generated_banner_and_verifies(con):
    doc = render.render_status(store.status(con))
    assert doc.startswith(render.GENERATED_BANNER)
    assert render.verify(doc) is True


def test_render_detects_a_hand_edit(con):
    doc = render.render_status(store.status(con))
    tampered = doc.replace("| 1 |", "| 99 |", 1)
    assert tampered != doc
    assert render.verify(tampered) is False


def test_render_lists_every_derived_state(con):
    doc = render.render_status(store.status(con))
    for state in models.DERIVED_STATES:
        assert state in doc


def test_render_covers_every_row(con):
    doc = render.render_status(store.status(con))
    rows = store.all_rows(con)
    for r in rows:
        assert r["slug"] in doc
