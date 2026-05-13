"""
E2E tests for seating chart API.
Covers: table CRUD, assign/unassign guests, deletion cascade bug.
"""


def _create_guest(client, name="אורח בדיקה"):
    r = client.post("/api/wedding/guests", json={"name": name, "status": "confirmed"})
    assert r.status_code == 201, r.text
    return r.json()


def _create_table(client, name="שולחן 1", capacity=8):
    r = client.post("/api/wedding/seating/tables", json={
        "name": name, "shape": "round", "capacity": capacity,
        "x": 100, "y": 100, "color": "rose",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _assign(client, table_id, guest_id, seat=1):
    r = client.post("/api/wedding/seating/assign", json={
        "table_id": table_id, "seat_number": seat, "guest_id": guest_id, "extra_seats": [],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _get_seating(client):
    r = client.get("/api/wedding/seating")
    assert r.status_code == 200, r.text
    return r.json()


# ─── Table CRUD ───────────────────────────────────────────────────────────────

def test_create_and_list_table(app_client):
    t = _create_table(app_client, name="שולחן יצירה")
    assert t["name"] == "שולחן יצירה"
    assert t["capacity"] == 8

    data = _get_seating(app_client)
    ids = [x["id"] for x in data["tables"]]
    assert t["id"] in ids


def test_update_table(app_client):
    t = _create_table(app_client, name="שולחן עדכון")
    r = app_client.put(f"/api/wedding/seating/tables/{t['id']}", json={"name": "שולחן חדש", "capacity": 10})
    assert r.status_code == 200
    assert r.json()["name"] == "שולחן חדש"
    assert r.json()["capacity"] == 10


def test_delete_table_no_guests(app_client):
    t = _create_table(app_client, name="שולחן למחיקה")
    r = app_client.delete(f"/api/wedding/seating/tables/{t['id']}")
    assert r.status_code == 204

    data = _get_seating(app_client)
    ids = [x["id"] for x in data["tables"]]
    assert t["id"] not in ids


# ─── Assign / Unassign ────────────────────────────────────────────────────────

def test_assign_guest_to_table(app_client):
    g = _create_guest(app_client, "אורח להושבה")
    t = _create_table(app_client, "שולחן הושבה")
    _assign(app_client, t["id"], g["id"], seat=1)

    data = _get_seating(app_client)
    unassigned_ids = [x["id"] for x in data["unassigned"]]
    assert g["id"] not in unassigned_ids

    target_table = next(x for x in data["tables"] if x["id"] == t["id"])
    seat_keys = list(target_table["assignments"].keys())
    assert "1" in seat_keys or 1 in seat_keys


def test_unassign_guest(app_client):
    g = _create_guest(app_client, "אורח לביטול הושבה")
    t = _create_table(app_client, "שולחן לביטול")
    _assign(app_client, t["id"], g["id"], seat=2)

    r = app_client.delete(f"/api/wedding/seating/assign/{g['id']}")
    assert r.status_code == 204

    data = _get_seating(app_client)
    unassigned_ids = [x["id"] for x in data["unassigned"]]
    assert g["id"] in unassigned_ids


# ─── Bug: delete table must clear assignments ─────────────────────────────────

def test_delete_table_releases_guests_to_unassigned():
    """
    When a seating table is deleted, all guests assigned to it must appear
    in the unassigned list again.  Previously, the DELETE endpoint did not
    remove the wedding_seating_assignments rows, so the guests were stuck in
    a ghost-assigned state and never showed up for re-seating.
    """
    pass  # placeholder — real test below uses app_client fixture


def test_delete_table_releases_guests_to_unassigned_real(app_client):
    g1 = _create_guest(app_client, "אורח תקוע 1")
    g2 = _create_guest(app_client, "אורח תקוע 2")
    t = _create_table(app_client, "שולחן למחיקה עם אורחים", capacity=10)

    _assign(app_client, t["id"], g1["id"], seat=1)
    _assign(app_client, t["id"], g2["id"], seat=2)

    # Confirm both are assigned (not in unassigned list)
    data = _get_seating(app_client)
    unassigned_ids_before = [x["id"] for x in data["unassigned"]]
    assert g1["id"] not in unassigned_ids_before, "g1 should be assigned before table deletion"
    assert g2["id"] not in unassigned_ids_before, "g2 should be assigned before table deletion"

    # Delete the table
    r = app_client.delete(f"/api/wedding/seating/tables/{t['id']}")
    assert r.status_code == 204

    # After deletion, both guests must appear in unassigned list
    data = _get_seating(app_client)
    unassigned_ids_after = [x["id"] for x in data["unassigned"]]
    assert g1["id"] in unassigned_ids_after, (
        "g1 still stuck as assigned after table was deleted — cascade bug!"
    )
    assert g2["id"] in unassigned_ids_after, (
        "g2 still stuck as assigned after table was deleted — cascade bug!"
    )
