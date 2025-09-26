
def test_statistics_page_loads(app_client):
    r = app_client.get("/finances/statistics")
    assert r.status_code == 200
    # Check presence of main header
    assert "סטטיסטיקות" in r.text or "נתונים" in r.text


def test_export_endpoint(app_client):
    r = app_client.get("/api/transactions/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def test_statistics_json_endpoints(app_client):
    # Main statistics JSON
    main = app_client.get("/api/statistics")
    assert main.status_code == 200
    body = main.json()
    for key in (
        "monthly_expenses",
        "top_expenses",
        "category_expenses",
        "user_expenses",
        "recurring_monthly",
        "cash_vs_credit",
        "total_expenses_month",
        "total_income_month",
        "balance_month",
        "total_transactions_month",
        "total_recurring_month",
        "total_regular_month",
        "total_expenses_6months",
        "categories_count",
    ):
        assert key in body

    # Monthly series: total and a specific category
    m_total = app_client.get("/api/statistics/monthly", params={"category": "total"})
    assert m_total.status_code == 200
    assert isinstance(m_total.json(), list)

    m_cat = app_client.get("/api/statistics/monthly", params={"category": "מכולת"})
    assert m_cat.status_code == 200
    assert isinstance(m_cat.json(), list)

    # Recurrences monthly series
    rec = app_client.get("/api/statistics/recurrences")
    assert rec.status_code == 200
    assert isinstance(rec.json(), list)
