from datetime import date


def _count_transactions(client, params=None):
    params = params or {}
    # Use API listing as a reliable count source
    resp = client.get("/api/transactions", params={
        "from_date": params.get("from_date"),
        "to_date": params.get("to_date"),
        "category_id": params.get("category_id"),
        "user_id": params.get("user_id"),
    })
    assert resp.status_code == 200
    return len(resp.json())


def test_transactions_page_loads(app_client):
    r = app_client.get("/finances/transactions")
    assert r.status_code == 200
    assert "עסקאות" in r.text


def test_filter_by_category_and_date(app_client, db_conn):
    # Fetch a real category and user
    cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    # Create a known transaction on today's date
    payload = {
        "date": date.today().isoformat(),
        "amount": 12.34,
        "category_id": cat_id,
        "user_id": usr_id,
        "account_id": None,
        "notes": "pytest-filter",
        "tags": "e2e,filter",
    }
    resp = app_client.post("/api/transactions", json=payload)
    assert resp.status_code == 200, resp.text
    created = resp.json()

    # Page with filters should include it
    page = app_client.get(
        "/finances/transactions",
        params={
            "category_id": cat_id,
            "user_id": usr_id,
            "date_from": payload["date"],
            "date_to": payload["date"],
            "transaction_type": "expense",
        },
    )
    assert page.status_code == 200
    assert "pytest-filter" in page.text

    # Cleanup: delete via API (safe for copied DB)
    del_resp = app_client.delete(f"/api/transactions/{created['id']}")
    assert del_resp.status_code == 200


def test_create_update_delete_transaction(app_client, db_conn):
    cat_id = db_conn.execute("SELECT id FROM categories ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    base_params = {"from_date": date.today().replace(day=1).isoformat()}
    before_count = _count_transactions(app_client, base_params)

    # Create
    create_payload = {
        "date": date.today().isoformat(),
        "amount": 50.0,
        "category_id": cat_id,
        "user_id": usr_id,
        "account_id": None,
        "notes": "pytest-create",
        "tags": "e2e,crud",
    }
    r = app_client.post("/api/transactions", json=create_payload)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["id"] > 0

    after_create_count = _count_transactions(app_client, base_params)
    assert after_create_count == before_count + 1

    # Update amount and category (sign preserved by API logic)
    upd = app_client.put(
        f"/api/transactions/{created['id']}",
        json={"amount": 75.25, "category_id": cat_id},
    )
    assert upd.status_code == 200, upd.text
    updated = upd.json()
    assert abs(updated["amount"]) == 75.25

    # Duplicate
    dup = app_client.post(f"/api/transactions/{created['id']}/duplicate")
    assert dup.status_code == 200, dup.text
    dup_id = dup.json()["id"]
    assert isinstance(dup_id, int)

    # Delete both
    d1 = app_client.delete(f"/api/transactions/{created['id']}")
    d2 = app_client.delete(f"/api/transactions/{dup_id}")
    assert d1.status_code == 200
    assert d2.status_code == 200

    final_count = _count_transactions(app_client, base_params)
    assert final_count == before_count


