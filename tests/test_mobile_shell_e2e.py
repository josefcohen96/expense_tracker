from datetime import date, timedelta


def _create_task(app_client, **fields):
    payload = {"title": "pytest-mobile task", **fields}
    r = app_client.post("/api/wedding/tasks", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_task_owner_is_validated_and_canonical(app_client):
    task = _create_task(app_client, owner="yosef")
    try:
        assert task["owner"] == "Yosef"

        r = app_client.put(f"/api/wedding/tasks/{task['id']}", json={"owner": "Karina"})
        assert r.status_code == 200 and r.json()["owner"] == "Karina"

        r = app_client.put(f"/api/wedding/tasks/{task['id']}", json={"owner": None})
        assert r.status_code == 200 and r.json()["owner"] is None

        r = app_client.put(f"/api/wedding/tasks/{task['id']}", json={"owner": "Somebody"})
        assert r.status_code == 422
    finally:
        app_client.delete(f"/api/wedding/tasks/{task['id']}")

    assert app_client.post("/api/wedding/tasks", json={"title": "x", "owner": "Nobody"}).status_code == 422
    assert app_client.post("/api/wedding/tasks", json={"title": "   "}).status_code == 422


def test_today_api_queues_overdue_and_upcoming_tasks(app_client):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    far = (date.today() + timedelta(days=40)).isoformat()
    late = _create_task(app_client, title="pytest-today late", due_date=yesterday)
    soon = _create_task(app_client, title="pytest-today soon", due_date=tomorrow)
    later = _create_task(app_client, title="pytest-today later", due_date=far)
    try:
        r = app_client.get("/api/today")
        assert r.status_code == 200, r.text
        body = r.json()
        by_id = {t["id"]: t for t in body["tasks"] if t["module"] == "wedding"}
        assert by_id[late["id"]]["urgency"] == "overdue"
        assert by_id[late["id"]]["due_label"] == "באיחור ביום"
        assert by_id[soon["id"]]["urgency"] == "soon"
        assert later["id"] not in by_id
        assert set(body["month"]) >= {"ym", "label", "expenses", "income"}
        assert "days_left" in body["wedding"]
    finally:
        for t in (late, soon, later):
            app_client.delete(f"/api/wedding/tasks/{t['id']}")


def test_quick_add_options_exclude_income_categories(app_client):
    r = app_client.get("/api/quick-add/options")
    assert r.status_code == 200, r.text
    body = r.json()
    names = {c["name"] for c in body["categories"]}
    assert "משכורת" not in names and "קליניקה" not in names
    assert body["categories"], "expense categories should be offered"
    assert [p["name"] for p in body["people"]][:2] == ["Yosef", "Karina"]
    assert body["people"][0]["color"] != body["people"][1]["color"]
    assert body["accounts"] and body["default_account_id"] in {a["id"] for a in body["accounts"]}
    assert {c["key"] for c in body["wedding_categories"]} >= {"general", "vendors"}


def test_root_renders_today_screen(app_client):
    r = app_client.get("/")
    assert r.status_code == 200
    assert "דחוף עכשיו" in r.text


def test_tasks_page_groups_by_urgency(app_client):
    yesterday = (date.today() - timedelta(days=3)).isoformat()
    late = _create_task(app_client, title="pytest-board late", due_date=yesterday, owner="Karina")
    loose = _create_task(app_client, title="pytest-board unassigned")
    try:
        r = app_client.get("/wedding/tasks")
        assert r.status_code == 200
        html = r.text
        assert 'data-group="overdue"' in html and "באיחור" in html
        assert "pytest-board late" in html
        assert "אף אחד לא לקח את זה" in html
        assert "חלוקת העומס" in html
    finally:
        app_client.delete(f"/api/wedding/tasks/{late['id']}")
        app_client.delete(f"/api/wedding/tasks/{loose['id']}")


def test_more_page_shows_wedding_settings(app_client):
    r = app_client.get("/more")
    assert r.status_code == 200
    assert 'data-setting="wedding_date"' in r.text
    assert 'data-setting="venue_capacity"' in r.text
    assert app_client.post("/api/wedding/settings", json={"key": "venue_capacity", "value": "abc"}).status_code == 422
    assert app_client.post("/api/wedding/settings", json={"key": "wedding_date", "value": "not-a-date"}).status_code == 422
