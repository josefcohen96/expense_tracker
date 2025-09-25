
def test_statistics_page_loads(app_client):
    r = app_client.get("/finances/statistics")
    assert r.status_code == 200
    # Check presence of key placeholders
    assert "total_expenses_month" in r.text or "נתונים" in r.text


def test_export_endpoint(app_client):
    r = app_client.get("/api/transactions/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


