
def test_service_worker_served(app_client):
    r = app_client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/javascript")


