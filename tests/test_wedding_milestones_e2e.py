"""
E2E tests for date-anchored wedding milestones (/wedding/milestones).

Milestone dates are the wedding date plus `offset_days` unless a `custom_date`
pins them. The test DB is shared across the session, so every test restores the
wedding date it changes and removes the milestones it creates.
"""
from datetime import date, timedelta

import pytest

from app.backend.app.services import wedding_plan

WEDDING_A = date(2030, 6, 15)
WEDDING_B = date(2030, 7, 1)
PINNED = "2030-01-10"
SEEDED_FLAG = "wedding_milestones_seeded"


def _set_wedding_date(client, value: date):
    r = client.post("/api/wedding/settings", json={"key": "wedding_date", "value": value.isoformat()})
    assert r.status_code == 200, r.text


def _milestones(client) -> dict:
    r = client.get("/api/wedding/milestones")
    assert r.status_code == 200, r.text
    return r.json()


def _find(client, milestone_id: int) -> dict:
    return next(m for m in _milestones(client)["milestones"] if m["id"] == milestone_id)


@pytest.fixture()
def wedding_date(app_client, db_conn):
    """Setter for the wedding date; puts the original value (or its absence) back."""
    row = db_conn.execute("SELECT value FROM wedding_settings WHERE key='wedding_date'").fetchone()
    original = row[0] if row else None
    yield lambda value: _set_wedding_date(app_client, value)
    if original is None:
        db_conn.execute("DELETE FROM wedding_settings WHERE key='wedding_date'")
    else:
        db_conn.execute("UPDATE wedding_settings SET value=? WHERE key='wedding_date'", (original,))
    db_conn.commit()


@pytest.fixture()
def milestone(app_client, wedding_date):
    """A milestone three weeks before the wedding, deleted afterwards."""
    wedding_date(WEDDING_A)
    r = app_client.post("/api/wedding/milestones", json={
        "title": "אבן דרך לבדיקה", "offset_days": -21, "kind": "general",
    })
    assert r.status_code == 201, r.text
    created = r.json()
    yield created
    app_client.delete(f"/api/wedding/milestones/{created['id']}")


def test_setting_wedding_date_provides_milestones(app_client, db_conn, wedding_date):
    had_rows = db_conn.execute("SELECT 1 FROM wedding_milestones LIMIT 1").fetchone() is not None
    had_flag = db_conn.execute("SELECT 1 FROM system_settings WHERE key=?", (SEEDED_FLAG,)).fetchone() is not None
    if not had_rows:
        # Seeding runs once; let it run for an empty table.
        db_conn.execute("DELETE FROM system_settings WHERE key=?", (SEEDED_FLAG,))
        db_conn.commit()
    try:
        wedding_date(WEDDING_A)
        view = _milestones(app_client)
        assert view["wedding_date"] == WEDDING_A.isoformat()
        assert view["wedding_date_label"] == "15.6.2030"
        assert view["milestones"], "setting a wedding date should leave milestones to show"
        assert all(m["date"] for m in view["milestones"])
        if not had_rows:
            titles = [m["title"] for m in view["milestones"]]
            assert sorted(titles) == sorted(t for t, _, _ in wedding_plan.DEFAULT_MILESTONES)
        assert db_conn.execute("SELECT 1 FROM system_settings WHERE key=?", (SEEDED_FLAG,)).fetchone()
    finally:
        if not had_rows:
            db_conn.execute("DELETE FROM wedding_milestones")
            if not had_flag:
                db_conn.execute("DELETE FROM system_settings WHERE key=?", (SEEDED_FLAG,))
            db_conn.commit()


def test_created_milestone_date_follows_wedding_date(app_client, wedding_date, milestone):
    assert milestone["date"] == (WEDDING_A - timedelta(days=21)).isoformat()
    assert milestone["adjusted"] is False
    assert milestone["offset_label"] == "-3 שבועות"
    assert milestone["status"] in ("next", "future")

    wedding_date(WEDDING_B)
    moved = _find(app_client, milestone["id"])
    assert moved["date"] == (WEDDING_B - timedelta(days=21)).isoformat()
    assert moved["date_label"] == "10.6"


def test_custom_date_pins_and_unpins(app_client, wedding_date, milestone):
    r = app_client.put(f"/api/wedding/milestones/{milestone['id']}", json={"custom_date": PINNED})
    assert r.status_code == 200, r.text
    pinned = r.json()
    assert pinned["date"] == PINNED
    assert pinned["adjusted"] is True

    # A pinned milestone stays put when the wedding moves.
    wedding_date(WEDDING_B)
    still = _find(app_client, milestone["id"])
    assert still["date"] == PINNED
    assert still["adjusted"] is True

    r = app_client.put(f"/api/wedding/milestones/{milestone['id']}", json={"custom_date": None})
    assert r.status_code == 200, r.text
    unpinned = r.json()
    assert unpinned["custom_date"] is None
    assert unpinned["adjusted"] is False
    assert unpinned["date"] == (WEDDING_B - timedelta(days=21)).isoformat()


def test_edit_title_and_offset(app_client, milestone):
    r = app_client.put(f"/api/wedding/milestones/{milestone['id']}", json={
        "title": "  שם חדש  ", "offset_days": -60,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "שם חדש"
    assert body["date"] == (WEDDING_A - timedelta(days=60)).isoformat()
    assert body["offset_label"] == "-2 חודשים"


def test_toggle_completed(app_client, milestone):
    r = app_client.put(f"/api/wedding/milestones/{milestone['id']}", json={"completed": 1})
    assert r.status_code == 200, r.text
    assert r.json()["completed"] == 1
    assert r.json()["status"] == "done"
    assert _find(app_client, milestone["id"])["status"] == "done"

    r = app_client.put(f"/api/wedding/milestones/{milestone['id']}", json={"completed": 0})
    assert r.status_code == 200, r.text
    assert r.json()["completed"] == 0
    assert r.json()["status"] in ("next", "future")


def test_delete_milestone(app_client, wedding_date):
    wedding_date(WEDDING_A)
    r = app_client.post("/api/wedding/milestones", json={"title": "למחיקה", "offset_days": -7})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]

    r = app_client.delete(f"/api/wedding/milestones/{mid}")
    assert r.status_code == 204
    assert all(m["id"] != mid for m in _milestones(app_client)["milestones"])
    r = app_client.put(f"/api/wedding/milestones/{mid}", json={"completed": 1})
    assert r.status_code == 404


@pytest.mark.parametrize("bad", ["not-a-date", "2030-13-45", "12.12.2030"])
def test_invalid_custom_date_rejected(app_client, milestone, bad):
    r = app_client.put(f"/api/wedding/milestones/{milestone['id']}", json={"custom_date": bad})
    assert r.status_code == 422, r.text
    assert _find(app_client, milestone["id"])["adjusted"] is False


def test_invalid_wedding_date_rejected(app_client):
    r = app_client.post("/api/wedding/settings", json={"key": "wedding_date", "value": "soon"})
    assert r.status_code == 422


def test_milestones_page_renders_rail(app_client, milestone):
    r = app_client.get("/wedding/milestones")
    assert r.status_code == 200, r.text
    html = r.text
    assert "לוח זמנים" in html
    assert "אבני דרך" in html
    assert "15.6.2030" in html          # derivation notice + the wedding card
    assert "אבן דרך לבדיקה" in html
    assert f'data-id="{milestone["id"]}"' in html
    assert "/wedding/timeline" in html


def test_milestones_page_without_wedding_date_shows_cta(app_client, db_conn, wedding_date, milestone):
    db_conn.execute("DELETE FROM wedding_settings WHERE key='wedding_date'")
    db_conn.commit()
    r = app_client.get("/wedding/milestones")
    assert r.status_code == 200, r.text
    assert "הגדירו תאריך כדי לראות לו״ז" in r.text
    assert 'id="ms-rail"' not in r.text
    assert "אבן דרך לבדיקה" not in r.text
