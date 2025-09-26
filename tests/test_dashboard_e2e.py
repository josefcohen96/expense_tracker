from datetime import date


def test_root_redirect_and_dashboard_loads(app_client):
    # Root should redirect to finances; TestClient follows redirects by default
    r = app_client.get("/")
    assert r.status_code == 200
    assert "לוח בקרה" in r.text or "finances" in r.text


def test_dashboard_kpis_and_recent_transactions(app_client, db_conn):
    # Pick an expense category (exclude income categories)
    cat_row = db_conn.execute(
        "SELECT id FROM categories WHERE name NOT IN ('משכורת','קליניקה') ORDER BY id LIMIT 1"
    ).fetchone()
    usr_row = db_conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    assert cat_row and usr_row

    note_txt = "pytest-dash"
    payload = {
        "date": date.today().isoformat(),
        "amount": 12.34,  # API will convert to negative for expense
        "category_id": cat_row[0],
        "user_id": usr_row[0],
        "account_id": None,
        "notes": note_txt,
        "tags": "dash,test",
    }
    created = app_client.post("/api/transactions", json=payload)
    assert created.status_code == 200, created.text

    # Load dashboard for the current month
    month_str = date.today().strftime("%Y-%m")
    r = app_client.get(f"/finances?month={month_str}")
    assert r.status_code == 200
    # KPI labels present
    assert "סה\"כ הוצאות החודש" in r.text
    assert "סה\"כ הכנסות החודש" in r.text
    assert "מספר עסקאות" in r.text
    # Recent transactions should include the new note
    assert note_txt in r.text

    # Cleanup: remove created transaction
    tx_id = created.json()["id"]
    d = app_client.delete(f"/api/transactions/{tx_id}")
    assert d.status_code == 200


def test_service_worker_endpoint(app_client):
    r = app_client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")


