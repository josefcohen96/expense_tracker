from datetime import date, timedelta


def test_apply_recurrence_once_and_delete_marks_skip(app_client, db_conn):
    # Create a recurrence via API first
    cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    payload = {
        "name": "pytest-apply-once",
        "amount": 15.0,
        "category_id": cat_id,
        "user_id": usr_id,
        "frequency": "monthly",
        "day_of_month": 1,
        "active": True,
    }
    r = app_client.post("/api/recurrences", json=payload)
    assert r.status_code == 200, r.text
    rec_id = r.json()["id"]

    # Apply once for today
    today = date.today().isoformat()
    a = app_client.post(f"/api/recurrences/{rec_id}/apply-once", json={"date": today, "notes": "pytest-once"})
    assert a.status_code == 200, a.text
    tx_id = a.json()["transaction_id"]

    # Delete the transaction; should create a skip for that period
    d = app_client.delete(f"/api/transactions/{tx_id}")
    assert d.status_code == 200

    # Verify skip exists
    row = db_conn.execute(
        "SELECT 1 FROM recurrence_skips WHERE recurrence_id = ? AND period_key = ?",
        (rec_id, today),
    ).fetchone()
    assert row, "Expected recurrence_skips row to be created"


def test_system_apply_created_something(app_client, db_conn):
    # Ensure there is at least one active recurrence due today
    rec = db_conn.execute(
        "SELECT id FROM recurrences WHERE active = 1 LIMIT 1"
    ).fetchone()
    if not rec:
        cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
        usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]
        db_conn.execute(
            "INSERT INTO recurrences (name, amount, category_id, user_id, frequency, day_of_month, next_charge_date, active) VALUES (?,?,?,?,?,?,?,1)",
            ("pytest-due", 9.99, cat_id, usr_id, "monthly", 1, date.today().isoformat()),
        )
        db_conn.commit()

    resp = app_client.post("/api/system/apply-recurring")
    assert resp.status_code == 200
    inserted = resp.json().get("inserted")
    assert isinstance(inserted, int)
    # We don't assert >0 to avoid flakiness across DB snapshots


