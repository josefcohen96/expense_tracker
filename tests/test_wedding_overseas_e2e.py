"""
E2E tests for הזמנות מחו״ל (/wedding/overseas): samples ordered from abroad.

The test DB is shared across the session, so every test restores the wedding
settings it changes and removes the items it creates. AUTH_ENABLED=0 means
there is no session user, so authors are passed explicitly.
"""
from datetime import date, timedelta

import pytest

from app.backend.app.services import hebrew_dates as hd
from app.backend.app.services import overseas

WEDDING = date(2030, 6, 15)
SETTING_KEYS = ("wedding_date", "overseas_lead_days")


@pytest.fixture()
def settings(app_client, db_conn):
    """Setter for wedding settings; puts the original values (or their absence) back."""
    originals = {}
    for key in SETTING_KEYS:
        row = db_conn.execute("SELECT value FROM wedding_settings WHERE key=?", (key,)).fetchone()
        originals[key] = row[0] if row else None
    # Posting a wedding date also seeds the default milestones once; undo that too.
    seeded_before = db_conn.execute(
        "SELECT 1 FROM system_settings WHERE key='wedding_milestones_seeded'"
    ).fetchone() is not None

    def set_value(key, value):
        return app_client.post("/api/wedding/settings", json={"key": key, "value": value})

    def clear(key):
        db_conn.execute("DELETE FROM wedding_settings WHERE key=?", (key,))
        db_conn.commit()

    set_value.clear = clear
    yield set_value
    for key, original in originals.items():
        db_conn.execute("DELETE FROM wedding_settings WHERE key=?", (key,))
        if original is not None:
            db_conn.execute("INSERT INTO wedding_settings (key, value) VALUES (?,?)", (key, original))
    if not seeded_before:
        db_conn.execute("DELETE FROM wedding_milestones")
        db_conn.execute("DELETE FROM system_settings WHERE key='wedding_milestones_seeded'")
    db_conn.commit()


@pytest.fixture()
def make_item(app_client):
    """Creates overseas items and deletes them afterwards."""
    created = []

    def make(**body):
        body.setdefault("title", "מגנטים לאורחים")
        r = app_client.post("/api/wedding/overseas", json=body)
        assert r.status_code == 201, r.text
        created.append(r.json()["id"])
        return r.json()

    yield make
    for item_id in created:
        app_client.delete(f"/api/wedding/overseas/{item_id}")


def _put(client, item_id, **body):
    return client.put(f"/api/wedding/overseas/{item_id}", json=body)


def _lane(view, key):
    return next(lane for lane in view["lanes"] if lane["key"] == key)


def test_overseas_page_renders_and_is_linked(app_client):
    r = app_client.get("/wedding/overseas")
    assert r.status_code == 200, r.text
    assert "הזמנות מחו״ל" in r.text
    tasks = app_client.get("/wedding/tasks")
    assert tasks.status_code == 200
    assert 'href="/wedding/overseas"' in tasks.text


def test_item_starts_in_to_order_lane(app_client, make_item):
    item = make_item(title="שלטי שולחן לבדיקה")
    assert item["stage"] == "to_order"
    assert item["ordered_at"] is None
    assert item["arrived_at"] is None
    view = app_client.get("/api/wedding/overseas").json()
    assert item["id"] in [i["id"] for i in _lane(view, "to_order")["items"]]
    page = app_client.get("/wedding/overseas").text
    assert "שלטי שולחן לבדיקה" in page
    lane_start = page.index('data-lane="to_order"')
    lane_end = page.index('data-lane="ordered"')
    assert lane_start < page.index("שלטי שולחן לבדיקה") < lane_end


def test_stage_transitions_set_and_clear_dates(app_client, make_item):
    today = date.today().isoformat()
    item = make_item()
    r = _put(app_client, item["id"], stage="ordered")
    assert r.status_code == 200, r.text
    assert r.json()["ordered_at"] == today
    assert r.json()["ordered_ago"] == "היום"
    r = _put(app_client, item["id"], stage="arrived")
    assert r.json()["arrived_at"] == today
    assert r.json()["ordered_at"] == today
    r = _put(app_client, item["id"], stage="approved")
    assert r.json()["stage"] == "approved"
    assert r.json()["ordered_at"] == today and r.json()["arrived_at"] == today
    r = _put(app_client, item["id"], stage="to_order")
    assert r.json()["ordered_at"] is None and r.json()["arrived_at"] is None


def test_stage_transition_back_to_ordered_clears_arrival():
    row = {"ordered_at": "2030-01-01", "arrived_at": "2030-01-10"}
    cols = overseas.stage_transition(row, "ordered", date(2030, 2, 1))
    assert cols == {"stage": "ordered", "ordered_at": "2030-01-01", "arrived_at": None}
    cols = overseas.stage_transition({"ordered_at": None, "arrived_at": None}, "arrived", date(2030, 2, 1))
    assert cols["ordered_at"] == cols["arrived_at"] == "2030-02-01"
    assert overseas.stage_transition(row, "rejected") == {"stage": "rejected"}


def test_invalid_stage_and_unknown_id(app_client, make_item):
    item = make_item()
    assert _put(app_client, item["id"], stage="flying").status_code == 422
    assert _put(app_client, 999999, stage="ordered").status_code == 404


def test_store_link_must_be_http(app_client, make_item):
    item = make_item(url="https://www.aliexpress.com/item/1.html")
    assert item["url"] == "https://www.aliexpress.com/item/1.html"
    r = app_client.post("/api/wedding/overseas", json={"title": "x", "url": "javascript:alert(1)"})
    assert r.status_code == 422
    assert _put(app_client, item["id"], url="ftp://x").status_code == 422
    assert _put(app_client, item["id"], url="  ").json()["url"] is None


def test_deadline_derives_from_wedding_date_and_lead_setting(app_client, db_conn, settings, make_item):
    # With an item on the page the empty state (whose copy mentions the big order) is not shown,
    # so the only source of the phrase below is the deadline banner.
    make_item()
    assert settings("wedding_date", WEDDING.isoformat()).status_code == 200
    settings.clear("overseas_lead_days")
    d = overseas.deadline(db_conn, today=date(2030, 1, 1))
    assert d["date"] == "2030-05-04"
    assert d["lead_weeks"] == 6
    assert d["label"] == "4 במאי"
    assert d["days_left"] == (date(2030, 5, 4) - date(2030, 1, 1)).days

    assert settings("overseas_lead_days", "28").status_code == 200
    assert overseas.deadline(db_conn, today=date(2030, 1, 1))["date"] == "2030-05-18"
    assert app_client.get("/api/wedding/overseas").json()["deadline"]["date"] == "2030-05-18"
    page = app_client.get("/wedding/overseas").text
    assert "ההזמנה הגדולה צריכה לצאת עד 18 במאי" in page

    r = settings("overseas_lead_days", "3")
    assert r.status_code == 422
    assert r.json()["detail"] == "זמן אספקה חייב להיות בין שבוע ל-20 שבועות"
    assert settings("overseas_lead_days", "abc").status_code == 422

    settings.clear("wedding_date")
    assert app_client.get("/api/wedding/overseas").json()["deadline"] is None
    assert "ההזמנה הגדולה" not in app_client.get("/wedding/overseas").text


def test_estimate_and_approved_total(app_client, make_item):
    priced = make_item(title="מניפות", sample_price=8, quantity_needed=150)
    assert priced["estimate"] == 1200
    assert priced["estimate_label"] == "₪1,200"
    no_qty = make_item(title="נרות", sample_price=5)
    assert no_qty["estimate"] is None
    no_price = make_item(title="סרטים", quantity_needed=40)
    assert no_price["estimate"] is None
    other = make_item(title="שקיות", sample_price=2, quantity_needed=100)

    for item in (priced, no_qty, no_price):
        _put(app_client, item["id"], stage="approved")
    view = app_client.get("/api/wedding/overseas").json()
    approved = _lane(view, "approved")
    mine = {priced["id"], no_qty["id"], no_price["id"]}
    assert mine <= {i["id"] for i in approved["items"]}
    expected = sum(i["estimate"] for i in approved["items"] if i["estimate"] is not None)
    assert approved["estimate_total"] == expected
    assert other["id"] not in {i["id"] for i in approved["items"]}
    # The unapproved item's 200 does not leak into the approved total.
    lane_items = [{"stage": "approved", "estimate": 1200.0}, {"stage": "to_order", "estimate": 200.0}]
    assert _lane({"lanes": overseas.lanes(lane_items)}, "approved")["estimate_total"] == 1200.0
    assert "סה״כ משוער" in app_client.get("/wedding/overseas").text


def test_comment_thread_and_author_validation(app_client, make_item):
    item = make_item()
    url = f"/api/wedding/overseas/{item['id']}/comments"
    r = app_client.post(url, json={"body": "קטן מדי", "author": "Karina"})
    assert r.status_code == 201, r.text
    comment = r.json()
    assert comment["author"] == "Karina"
    assert comment["item_id"] == item["id"]
    assert set(comment) == {"id", "item_id", "author", "body", "created_at"}

    view = app_client.get("/api/wedding/overseas").json()
    stored = next(i for i in _lane(view, "to_order")["items"] if i["id"] == item["id"])
    assert stored["comment_count"] == 1
    assert stored["comments"][0]["body"] == "קטן מדי"
    assert "קטן מדי" in app_client.get("/wedding/overseas").text

    assert app_client.post(url, json={"body": "שלום", "author": "Someone"}).status_code == 422
    assert app_client.post(url, json={"body": ""}).status_code == 422
    assert app_client.post(url, json={"body": "   "}).status_code == 422
    assert app_client.post("/api/wedding/overseas/999999/comments", json={"body": "x"}).status_code == 404


def test_delete_cascades_comments(app_client, db_conn):
    r = app_client.post("/api/wedding/overseas", json={"title": "פריט למחיקה", "created_by": "Yosef"})
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert r.json()["created_by"] == "Yosef"
    app_client.post(f"/api/wedding/overseas/{item_id}/comments", json={"body": "א", "author": "Yosef"})
    app_client.post(f"/api/wedding/overseas/{item_id}/comments", json={"body": "ב"})
    assert db_conn.execute(
        "SELECT COUNT(*) FROM wedding_overseas_comments WHERE item_id=?", (item_id,)
    ).fetchone()[0] == 2
    assert app_client.delete(f"/api/wedding/overseas/{item_id}").status_code == 204
    assert db_conn.execute(
        "SELECT COUNT(*) FROM wedding_overseas_comments WHERE item_id=?", (item_id,)
    ).fetchone()[0] == 0
    assert db_conn.execute("SELECT 1 FROM wedding_overseas_items WHERE id=?", (item_id,)).fetchone() is None


def test_ago_label():
    today = date(2030, 3, 1)
    ago = lambda n: hd.ago_label(today - timedelta(days=n), today)  # noqa: E731
    assert ago(0) == "היום"
    assert ago(1) == "אתמול"
    assert ago(2) == "לפני יומיים"
    assert ago(5) == "לפני 5 ימים"
    assert ago(14) == "לפני שבועיים"
    assert ago(21) == "לפני 3 שבועות"
    assert ago(90) == "לפני 3 חודשים"
