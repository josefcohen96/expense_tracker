from datetime import date


def test_dashboard_month_param_and_invalid_fallback(app_client):
    # Valid month format
    month = date.today().strftime("%Y-%m")
    r = app_client.get(f"/finances?month={month}")
    assert r.status_code == 200

    # Invalid month format should still load (fallback internally)
    r2 = app_client.get("/finances?month=BAD-FORMAT")
    assert r2.status_code == 200


def test_transactions_pagination_params(app_client):
    # First page
    r1 = app_client.get("/finances/transactions", params={"page": 1, "per_page": 5})
    assert r1.status_code == 200
    # Second page should also load (even if no more data)
    r2 = app_client.get("/finances/transactions", params={"page": 2, "per_page": 5})
    assert r2.status_code == 200


