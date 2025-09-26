
def test_recurrences_active_page_loads(app_client):
    r = app_client.get("/finances/recurrences/active")
    assert r.status_code == 200
    assert "הוצאות קבועות פעילות" in r.text


