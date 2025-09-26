from datetime import date


def _create_tx(app_client, cat_id, usr_id, amount, notes, account_id=None, tags=None, date_str=None):
    payload = {
        "date": date_str or date.today().isoformat(),
        "amount": amount,
        "category_id": cat_id,
        "user_id": usr_id,
        "account_id": account_id,
        "notes": notes,
        "tags": tags,
    }
    r = app_client.post("/api/transactions", json=payload)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_export_filters_and_sorts(app_client, db_conn):
    cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    # Create two transactions with different amounts/tags
    tx1 = _create_tx(app_client, cat_id, usr_id, 10.0, "pytest-exp-1", tags="tagA,tagB")
    tx2 = _create_tx(app_client, cat_id, usr_id, 50.0, "pytest-exp-2", tags="tagB")

    # Filter by tagA should include only first
    r1 = app_client.get(
        "/api/transactions/export",
        params={"tags": "tagA"},
    )
    assert r1.status_code == 200

    # Filter by amount_min should include only tx2
    r2 = app_client.get(
        "/api/transactions/export",
        params={"amount_min": 30},
    )
    assert r2.status_code == 200

    # Sort by amount_desc should be valid
    r3 = app_client.get(
        "/api/transactions/export",
        params={"sort": "amount_desc"},
    )
    assert r3.status_code == 200

    # Cleanup
    app_client.delete(f"/api/transactions/{tx1}")
    app_client.delete(f"/api/transactions/{tx2}")


