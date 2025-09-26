from datetime import date


def test_update_nonexistent_transaction_returns_404(app_client):
    r = app_client.put("/api/transactions/999999", json={"amount": 12.3})
    assert r.status_code in (404, 400)


def test_amount_sign_changes_with_category_switch(app_client, db_conn):
    expense_cat = db_conn.execute("SELECT id FROM categories WHERE name NOT IN ('משכורת','קליניקה') ORDER BY id LIMIT 1").fetchone()[0]
    income_cat = db_conn.execute("SELECT id FROM categories WHERE name IN ('משכורת','קליניקה') ORDER BY id LIMIT 1").fetchone()
    if not income_cat:
        db_conn.execute("INSERT INTO categories (name) VALUES ('משכורת')")
        db_conn.commit()
        income_cat = db_conn.execute("SELECT id FROM categories WHERE name = 'משכורת' ORDER BY id LIMIT 1").fetchone()
    income_cat = income_cat[0]
    usr_id = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()[0]

    # Create as expense (negative)
    create = app_client.post(
        "/api/transactions",
        json={
            "date": date.today().isoformat(),
            "amount": 100.0,
            "category_id": expense_cat,
            "user_id": usr_id,
            "account_id": None,
            "notes": "pytest-sign",
            "tags": "",
        },
    )
    assert create.status_code == 200, create.text
    tx = create.json()
    assert tx["amount"] < 0

    # Switch category to income should flip to positive (preserving abs)
    upd = app_client.put(f"/api/transactions/{tx['id']}", json={"category_id": income_cat, "amount": 200.0})
    assert upd.status_code == 200, upd.text
    updated = upd.json()
    assert updated["amount"] > 0 and abs(updated["amount"]) == 200.0

    # Cleanup
    app_client.delete(f"/api/transactions/{tx['id']}")


