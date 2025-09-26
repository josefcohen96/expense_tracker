from datetime import date


def test_backup_list_create_and_delete(app_client):
    # Initial list
    r0 = app_client.get("/api/backup")
    assert r0.status_code == 200
    assert isinstance(r0.json().get("backups", []), list)

    # Create a new dated backup (directory)
    r1 = app_client.post("/api/backup/create")
    assert r1.status_code == 200, r1.text
    payload = r1.json()
    folder_name = payload.get("file")
    assert folder_name and isinstance(folder_name, str)
    assert payload.get("message")

    # It should appear in listing
    r2 = app_client.get("/api/backup")
    assert r2.status_code == 200
    backups = r2.json()["backups"]
    names = [b.get("file") for b in backups]
    assert folder_name in names

    # Delete the created backup directory
    r3 = app_client.delete(f"/api/backup/{folder_name}")
    assert r3.status_code == 200


def test_monthly_backup_create_and_download(app_client):
    y = date.today().year
    m = date.today().month
    r = app_client.post(f"/api/backup/monthly/{y}/{m}")
    assert r.status_code == 200, r.text
    body = r.json()
    fname = body.get("file")
    assert fname and fname.endswith(".xlsx")

    d = app_client.get(f"/api/backup/download-excel/{fname}")
    assert d.status_code == 200
    assert d.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


