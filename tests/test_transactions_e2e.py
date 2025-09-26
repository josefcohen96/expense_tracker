from datetime import date


def _count_transactions(client, params=None):
    params = params or {}
    # Use API listing as a reliable count source
    resp = client.get("/api/transactions", params={
        # Only include provided params to avoid FastAPI 422 on empty strings
        **({"from_date": params["from_date"]} if params.get("from_date") else {}),
        **({"to_date": params["to_date"]} if params.get("to_date") else {}),
        **({"category_id": params["category_id"]} if params.get("category_id") is not None else {}),
        **({"user_id": params["user_id"]} if params.get("user_id") is not None else {}),
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


def test_transactions_inline_row_partial_routes(app_client, db_conn):
    # Create a transaction to operate on
    cat_id = db_conn.execute("SELECT id FROM categories WHERE name NOT IN ('משכורת','קליניקה') ORDER BY id LIMIT 1").fetchone()[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    payload = {
        "date": date.today().isoformat(),
        "amount": 33.33,
        "category_id": cat_id,
        "user_id": usr_id,
        "account_id": None,
        "notes": "pytest-inline",
        "tags": "e2e,inline",
    }
    resp = app_client.post("/api/transactions", json=payload)
    assert resp.status_code == 200, resp.text
    tx_id = resp.json()["id"]

    # Fetch row partial (read)
    row_read = app_client.get(f"/transactions/{tx_id}/row")
    assert row_read.status_code == 200
    assert "pytest-inline" in row_read.text

    # Fetch edit partial
    row_edit = app_client.get(f"/transactions/{tx_id}/edit-inline")
    assert row_edit.status_code == 200
    assert f"form=\"edit-{tx_id}\"" in row_edit.text

    # Save edit via partial POST (change amount and notes)
    form_data = {
        "date": payload["date"],
        "amount": "44.44",
        "category_id": str(cat_id),
        "user_id": str(usr_id),
        "account_id": "",
        "notes": "pytest-inline-upd",
        "tags": "e2e,inline",
    }
    row_saved = app_client.post(
        f"/transactions/{tx_id}/edit-inline",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert row_saved.status_code == 200
    assert "pytest-inline-upd" in row_saved.text

    # Delete via partial
    row_del = app_client.post(f"/transactions/{tx_id}/delete-inline")
    assert row_del.status_code == 200


