"""
E2E tests for the wedding vendors API and page.
Covers: CRUD, quote items, page rendering, edge cases.
"""


# ─── Page rendering ──────────────────────────────────────────────────────────

def test_vendors_page_loads(app_client):
    r = app_client.get("/wedding/vendors")
    assert r.status_code == 200
    assert "ספקים" in r.text


# ─── Vendor CRUD ─────────────────────────────────────────────────────────────

def _create_vendor(client, **kwargs):
    payload = {"name": "ספק בדיקה", "category": "venue", "status": "not_contacted", **kwargs}
    r = client.post("/api/wedding/vendors", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list_vendor(app_client):
    v = _create_vendor(app_client, name="אולם המלך", category="venue")
    assert v["name"] == "אולם המלך"
    assert v["category"] == "venue"
    assert v["id"] is not None

    r = app_client.get("/api/wedding/vendors")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert v["id"] in ids


def test_create_vendor_all_fields(app_client):
    v = _create_vendor(
        app_client,
        name="ספק מלא",
        category="photographer",
        contact_name="יוסי",
        phone="050-1234567",
        price_quoted=5000,
        status="quote_received",
        deposit_amount=1000,
        notes="הערה",
        location="תל אביב",
        instagram_url="https://instagram.com/test",
    )
    assert v["contact_name"] == "יוסי"
    assert v["phone"] == "050-1234567"
    assert v["price_quoted"] == 5000
    assert v["deposit_amount"] == 1000


def test_update_vendor(app_client):
    v = _create_vendor(app_client, name="ספק לעדכון")
    r = app_client.put(f"/api/wedding/vendors/{v['id']}", json={
        "name": "ספק מעודכן",
        "status": "deal_closed",
        "price_quoted": 8000,
    })
    assert r.status_code == 200
    updated = r.json()
    assert updated["name"] == "ספק מעודכן"
    assert updated["status"] == "deal_closed"
    assert updated["price_quoted"] == 8000


def test_update_vendor_not_found(app_client):
    r = app_client.put("/api/wedding/vendors/999999", json={"name": "לא קיים"})
    assert r.status_code == 404


def test_delete_vendor(app_client):
    v = _create_vendor(app_client, name="ספק למחיקה")
    r = app_client.delete(f"/api/wedding/vendors/{v['id']}")
    assert r.status_code == 204

    r2 = app_client.get("/api/wedding/vendors")
    ids = [x["id"] for x in r2.json()]
    assert v["id"] not in ids


def test_vendor_name_with_single_quote(app_client):
    """Single-quote in vendor name must not break anything."""
    v = _create_vendor(app_client, name="דיג'יי רועי", category="dj")
    assert v["name"] == "דיג'יי רועי"

    r = app_client.get(f"/api/wedding/vendors")
    names = [x["name"] for x in r.json()]
    assert "דיג'יי רועי" in names


def test_vendor_name_with_html_chars(app_client):
    """HTML special chars in vendor name must be stored and returned correctly."""
    v = _create_vendor(app_client, name='ספק <test> & "more"', category="catering")
    assert v["name"] == 'ספק <test> & "more"'


# ─── Status transitions ──────────────────────────────────────────────────────

def test_all_vendor_statuses(app_client):
    statuses = ["not_contacted", "quote_received", "contract_signed",
                "deal_closed", "deposit_paid", "fully_paid"]
    v = _create_vendor(app_client)
    for st in statuses:
        r = app_client.put(f"/api/wedding/vendors/{v['id']}", json={"status": st})
        assert r.status_code == 200, f"status {st} failed: {r.text}"
        assert r.json()["status"] == st


# ─── Quote items ─────────────────────────────────────────────────────────────

def test_quote_items_replace_and_recalc(app_client):
    v = _create_vendor(app_client, name="ספק עם מרכיבים")
    vid = v["id"]

    items = [
        {"description": "שירות", "quantity": 1, "unit_price": 1000, "apply_vat": 0},
        {"description": "ציוד",  "quantity": 2, "unit_price": 500,  "apply_vat": 1},
    ]
    r = app_client.put(f"/api/wedding/vendors/{vid}/quote-items", json=items)
    assert r.status_code == 200
    data = r.json()

    # pre-vat: 1000 + 1000 = 2000; vat on second item: 1000 * 0.17 = 170; total: 2170
    assert abs(data["total"] - 2170.0) < 0.01
    assert len(data["items"]) == 2

    # price_quoted on vendor should be updated
    vendor = app_client.get(f"/api/wedding/vendors").json()
    updated = next(x for x in vendor if x["id"] == vid)
    assert abs(updated["price_quoted"] - 2170.0) < 0.01


def test_quote_items_clear(app_client):
    v = _create_vendor(app_client, name="ספק לניקוי מרכיבים")
    vid = v["id"]

    app_client.put(f"/api/wedding/vendors/{vid}/quote-items", json=[
        {"description": "פריט", "quantity": 1, "unit_price": 500, "apply_vat": 0}
    ])
    r = app_client.put(f"/api/wedding/vendors/{vid}/quote-items", json=[])
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_quote_items_vendor_not_found(app_client):
    r = app_client.put("/api/wedding/vendors/999999/quote-items", json=[])
    assert r.status_code == 404


# ─── Vendor detail page ───────────────────────────────────────────────────────

def test_vendor_detail_page_loads(app_client):
    v = _create_vendor(app_client, name="ספק לפרטים")
    r = app_client.get(f"/wedding/vendors/{v['id']}")
    assert r.status_code == 200
    assert "ספק לפרטים" in r.text


def test_vendor_detail_page_not_found(app_client):
    r = app_client.get("/wedding/vendors/999999")
    assert r.status_code == 404


# ─── Delete cascades quote items ─────────────────────────────────────────────

def test_delete_vendor_cascades_quote_items(app_client, db_conn):
    v = _create_vendor(app_client, name="ספק עם מרכיבים למחיקה")
    vid = v["id"]
    app_client.put(f"/api/wedding/vendors/{vid}/quote-items", json=[
        {"description": "פריט", "quantity": 1, "unit_price": 100, "apply_vat": 0}
    ])

    app_client.delete(f"/api/wedding/vendors/{vid}")
    count = db_conn.execute(
        "SELECT COUNT(*) FROM vendor_quote_items WHERE vendor_id=?", (vid,)
    ).fetchone()[0]
    assert count == 0
