from datetime import date


def test_recurrences_page_loads(app_client):
    r = app_client.get("/finances/recurrences")
    assert r.status_code == 200
    assert "הוצאות קבועות" in r.text or "recurrences" in r.text


def test_create_update_delete_recurrence(app_client, db_conn):
    cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    # Create
    payload = {
        "name": "pytest-recurrence",
        "amount": 123.45,
        "category_id": cat_id,
        "user_id": usr_id,
        "start_date": date.today().isoformat(),
        "frequency": "monthly",
        "day_of_month": 1,
        "active": True,
    }
    r = app_client.post("/api/recurrences", json=payload)
    assert r.status_code == 200, r.text
    created = r.json()
    rec_id = created["id"]
    assert rec_id > 0

    # Update
    upd = app_client.patch(f"/api/recurrences/{rec_id}", json={"amount": 222.22, "active": False})
    assert upd.status_code == 200, upd.text
    updated = upd.json()
    assert updated["amount"] == 222.22
    assert updated["active"] is False

    # Delete
    d = app_client.delete(f"/api/recurrences/{rec_id}")
    assert d.status_code == 200


def test_recurrences_filters_and_inline_toggle(app_client, db_conn):
    # Ensure page responds to filters
    page = app_client.get("/finances/recurrences", params={"only_active": "1"})
    assert page.status_code == 200

    # Create a small recurrence to toggle
    cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]
    payload = {
        "name": "pytest-rec-toggle",
        "amount": 10.0,
        "category_id": cat_id,
        "user_id": usr_id,
        "start_date": date.today().isoformat(),
        "frequency": "monthly",
        "day_of_month": 1,
        "active": True,
    }
    r = app_client.post("/api/recurrences", json=payload)
    assert r.status_code == 200, r.text
    rec_id = r.json()["id"]

    # Toggle via partial
    row_html = app_client.post(f"/recurrences/{rec_id}/toggle-active")
    assert row_html.status_code == 200
    # Get row again should succeed
    row_again = app_client.get(f"/recurrences/{rec_id}/row")
    assert row_again.status_code == 200

    # Cleanup
    d = app_client.delete(f"/api/recurrences/{rec_id}")
    assert d.status_code == 200


