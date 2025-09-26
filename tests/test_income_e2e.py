from datetime import date


def test_income_page_loads(app_client):
    r = app_client.get("/finances/income")
    assert r.status_code == 200
    assert "הכנסות" in r.text


def test_income_inline_row_partials_and_positive_amounts(app_client, db_conn):
    # Use an income category (משכורת or קליניקה)
    cat_row = db_conn.execute("SELECT id FROM categories WHERE name IN ('משכורת','קליניקה') ORDER BY id LIMIT 1").fetchone()
    usr_row = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    if not cat_row:
        # Ensure an income category exists for the test DB copy
        db_conn.execute("INSERT INTO categories (name) VALUES ('משכורת')")
        db_conn.commit()
        cat_row = db_conn.execute("SELECT id FROM categories WHERE name = 'משכורת' ORDER BY id LIMIT 1").fetchone()
    assert cat_row and usr_row

    payload = {
        "date": date.today().isoformat(),
        "amount": 111.11,  # stays positive for income
        "category_id": cat_row[0],
        "user_id": usr_row[0],
        "account_id": None,
        "notes": "pytest-income",
        "tags": "e2e,income",
    }
    created = app_client.post("/api/transactions", json=payload)
    assert created.status_code == 200, created.text
    tx = created.json()
    tx_id = tx["id"]
    assert tx["amount"] > 0

    # Page should contain it
    page = app_client.get("/finances/income")
    assert page.status_code == 200
    assert "pytest-income" in page.text

    # Partials: read
    row_read = app_client.get(f"/income/{tx_id}/row")
    assert row_read.status_code == 200
    assert "pytest-income" in row_read.text

    # Edit partial
    row_edit = app_client.get(f"/income/{tx_id}/edit-inline")
    assert row_edit.status_code == 200
    assert f"form=\"edit-{tx_id}\"" in row_edit.text

    # Save edit: update amount and notes
    form_data = {
        "date": payload["date"],
        "amount": "222.22",
        "category_id": str(cat_row[0]),
        "user_id": str(usr_row[0]),
        "account_id": "",
        "notes": "pytest-income-upd",
        "tags": "e2e,income",
    }
    row_saved = app_client.post(
        f"/income/{tx_id}/edit-inline",
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert row_saved.status_code == 200
    assert "pytest-income-upd" in row_saved.text

    # Delete via partial
    row_del = app_client.post(f"/income/{tx_id}/delete-inline")
    assert row_del.status_code == 200


