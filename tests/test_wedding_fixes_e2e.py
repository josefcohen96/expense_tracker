"""
E2E tests covering wedding-section bug fixes.

These tests verify the regressions identified in the audit are fixed:
  - update endpoints accept null to clear nullable fields
  - delete_guest cleans up seating + room assignments
  - invite link uses request host (not hard-coded production URL) when no env override
  - room capacity is enforced server-side
  - seating assign validates seat numbers & is atomic
  - room max_capacity must be >= 1
  - quote-items: clearing the list resets vendor.price_quoted to 0
  - file upload rejects content with mismatched magic bytes
"""
import os
import io


def _create_guest(client, name="טסט", **extra):
    payload = {"name": name, "status": "confirmed", **extra}
    r = client.post("/api/wedding/guests", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_table(client, name="שולחן 1", capacity=8):
    r = client.post("/api/wedding/seating/tables", json={
        "name": name, "shape": "round", "capacity": capacity,
        "x": 100, "y": 100, "color": "rose",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _create_room(client, name="חדר 1", capacity=2):
    r = client.post("/api/wedding/rooms", json={
        "name": name, "room_type": "יחידים", "max_capacity": capacity,
    })
    assert r.status_code == 201, r.text
    return r.json()


# ─── update endpoints accept None to clear nullable fields ───────────────────

def test_update_guest_can_clear_phone(app_client):
    g = _create_guest(app_client, name="עם טלפון", phone="050-1234567")
    assert g["phone"] == "050-1234567"
    r = app_client.put(f"/api/wedding/guests/{g['id']}", json={"phone": None})
    assert r.status_code == 200
    assert r.json()["phone"] is None


def test_update_vendor_can_clear_notes(app_client):
    r = app_client.post("/api/wedding/vendors", json={
        "name": "ספק להעריך", "category": "venue", "notes": "הערה ראשונית",
    })
    assert r.status_code == 201
    vid = r.json()["id"]
    r = app_client.put(f"/api/wedding/vendors/{vid}", json={"notes": None})
    assert r.status_code == 200
    assert r.json()["notes"] is None


# ─── delete_guest cleans up seating + room assignments ───────────────────────

def test_delete_guest_clears_seating_assignment(app_client):
    g = _create_guest(app_client, name="למחיקה")
    t = _create_table(app_client, name="שולחן מחיקה")
    r = app_client.post("/api/wedding/seating/assign", json={
        "table_id": t["id"], "seat_number": 1, "guest_id": g["id"], "extra_seats": [],
    })
    assert r.status_code == 201
    # Now delete the guest
    r = app_client.delete(f"/api/wedding/guests/{g['id']}")
    assert r.status_code == 204
    # Seating data should no longer reference this guest
    seating = app_client.get("/api/wedding/seating").json()
    for tbl in seating["tables"]:
        for sn, assg in tbl.get("assignments", {}).items():
            assert assg["guest_id"] != g["id"], "Seating assignment leaked after guest delete"


def test_delete_guest_clears_room_assignment(app_client):
    g = _create_guest(app_client, name="עם חדר", staying_overnight=1)
    room = _create_room(app_client, name="חדר מחיקה", capacity=4)
    r = app_client.post(f"/api/wedding/rooms/{room['id']}/assign/{g['id']}")
    assert r.status_code == 201
    # Delete the guest
    r = app_client.delete(f"/api/wedding/guests/{g['id']}")
    assert r.status_code == 204
    # Room listing should no longer show this guest
    rooms = app_client.get("/api/wedding/rooms").json()
    for rm in rooms:
        for a in rm.get("assigned", []):
            assert a["guest_id"] != g["id"], "Room assignment leaked after guest delete"


# ─── invite link reflects request host instead of hard-coded prod URL ────────

def test_invite_link_uses_request_host(app_client, monkeypatch):
    # Ensure no env override
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    g = _create_guest(app_client, name="עם הזמנה")
    r = app_client.post(f"/api/wedding/guests/{g['id']}/generate-invite")
    assert r.status_code == 200, r.text
    link = r.json()["link"]
    # TestClient base URL is http://testserver
    assert link.startswith("http://testserver/invite/"), link


def test_invite_link_respects_env_override(app_client, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    g = _create_guest(app_client, name="ENV override")
    r = app_client.post(f"/api/wedding/guests/{g['id']}/generate-invite")
    assert r.status_code == 200
    link = r.json()["link"]
    assert link.startswith("https://example.com/invite/"), link


# ─── room capacity enforced server-side ──────────────────────────────────────

def test_room_assign_fails_when_full(app_client):
    g1 = _create_guest(app_client, name="ר1", staying_overnight=1)
    g2 = _create_guest(app_client, name="ר2", staying_overnight=1)
    room = _create_room(app_client, name="חדר קטן", capacity=1)
    r = app_client.post(f"/api/wedding/rooms/{room['id']}/assign/{g1['id']}")
    assert r.status_code == 201
    # Second guest should be rejected
    r2 = app_client.post(f"/api/wedding/rooms/{room['id']}/assign/{g2['id']}")
    assert r2.status_code == 400


def test_room_assign_rejects_declined_guest(app_client):
    g = _create_guest(app_client, name="declined", status="declined")
    room = _create_room(app_client, name="חדר ל-declined", capacity=2)
    r = app_client.post(f"/api/wedding/rooms/{room['id']}/assign/{g['id']}")
    assert r.status_code == 400


def test_create_room_rejects_zero_capacity(app_client):
    r = app_client.post("/api/wedding/rooms", json={"name": "אפס", "max_capacity": 0})
    assert r.status_code == 400


# ─── seating assign validates seats ──────────────────────────────────────────

def test_seating_assign_rejects_out_of_range_seat(app_client):
    g = _create_guest(app_client, name="מחוץ")
    t = _create_table(app_client, name="טבלה קטנה", capacity=4)
    r = app_client.post("/api/wedding/seating/assign", json={
        "table_id": t["id"], "seat_number": 99, "guest_id": g["id"], "extra_seats": [],
    })
    assert r.status_code == 400


def test_seating_assign_dedupes_extra_seats(app_client):
    g = _create_guest(app_client, name="ddedupe")
    t = _create_table(app_client, name="dedupe table", capacity=8)
    r = app_client.post("/api/wedding/seating/assign", json={
        "table_id": t["id"], "seat_number": 1, "guest_id": g["id"], "extra_seats": [1, 2, 2, 3],
    })
    assert r.status_code == 201
    seats = r.json().get("seats")
    assert seats == [1, 2, 3], f"unique seats expected, got {seats}"


# ─── quote items: clearing resets vendor price_quoted ────────────────────────

def test_clearing_quote_items_resets_price_quoted(app_client):
    r = app_client.post("/api/wedding/vendors", json={
        "name": "ספק עם פריטים", "category": "catering",
    })
    vid = r.json()["id"]
    # Add an item
    r = app_client.put(f"/api/wedding/vendors/{vid}/quote-items", json=[
        {"description": "אוכל", "quantity": 1, "unit_price": 5000, "apply_vat": 0},
    ])
    assert r.status_code == 200
    assert r.json()["total"] == 5000
    # Confirm vendor's price_quoted reflects it
    v = next(x for x in app_client.get("/api/wedding/vendors").json() if x["id"] == vid)
    assert v["price_quoted"] == 5000
    # Now clear all items — vendor price_quoted should reset to 0
    r = app_client.put(f"/api/wedding/vendors/{vid}/quote-items", json=[])
    assert r.status_code == 200
    v = next(x for x in app_client.get("/api/wedding/vendors").json() if x["id"] == vid)
    assert v["price_quoted"] == 0, f"price_quoted should reset to 0, got {v['price_quoted']}"


# ─── file upload magic-byte sniffing ─────────────────────────────────────────

def test_file_upload_rejects_extension_content_mismatch(app_client):
    r = app_client.post("/api/wedding/vendors", json={"name": "ספק קבצים", "category": "venue"})
    vid = r.json()["id"]
    # Send an HTML payload disguised as PDF
    fake = io.BytesIO(b"<html><script>alert(1)</script></html>")
    r = app_client.post(
        f"/api/wedding/vendors/{vid}/files",
        files={"file": ("evil.pdf", fake, "application/pdf")},
    )
    assert r.status_code == 400, r.text
    assert "תוכן" in r.text or "magic" in r.text.lower() or "תואם" in r.text


def test_file_upload_accepts_real_pdf(app_client):
    r = app_client.post("/api/wedding/vendors", json={"name": "ספק PDF", "category": "venue"})
    vid = r.json()["id"]
    # Minimal PDF — starts with %PDF- magic bytes
    pdf_bytes = b"%PDF-1.4\n%real-ish content"
    r = app_client.post(
        f"/api/wedding/vendors/{vid}/files",
        files={"file": ("real.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
    )
    assert r.status_code == 201, r.text


# ─── declining a guest clears their assignments ──────────────────────────────

def test_declining_guest_clears_seating(app_client):
    g = _create_guest(app_client, name="declined-flow", status="confirmed")
    t = _create_table(app_client, name="טבלה לקליין", capacity=8)
    r = app_client.post("/api/wedding/seating/assign", json={
        "table_id": t["id"], "seat_number": 1, "guest_id": g["id"], "extra_seats": [],
    })
    assert r.status_code == 201
    # Now flip status to declined
    r = app_client.put(f"/api/wedding/guests/{g['id']}", json={"status": "declined"})
    assert r.status_code == 200
    # Their seating row should be gone
    seating = app_client.get("/api/wedding/seating").json()
    for tbl in seating["tables"]:
        for sn, assg in tbl.get("assignments", {}).items():
            assert assg["guest_id"] != g["id"], "Seating not cleared after decline"
