
def test_statistics_cache_endpoints(app_client):
    # Ensure stats ok
    s = app_client.get("/api/statistics")
    assert s.status_code == 200

    # Cache stats
    stats = app_client.get("/api/statistics/cache-stats")
    assert stats.status_code == 200
    body = stats.json()
    assert "total_entries" in body

    # Clear cache
    clr = app_client.post("/api/statistics/clear-cache")
    assert clr.status_code == 200


