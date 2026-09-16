"""
E2E tests for the guest count as the engine of the wedding plan:
  - the catering vendor's portions_ordered round-trips through the vendor API
  - /wedding/guests shows the confirmed headcount once a guest exists
  - the catering card appears only while portions differ from confirmed people

The shared test DB may already hold guests and vendors, so assertions compare
against the live headcount instead of fixed numbers.
"""
from app.backend.app.services import wedding_plan

CATERING_CARD = "התפריט נסגר על"


def _create_vendor(client, **kwargs):
    payload = {"name": "קייטרינג בדיקה", "category": "catering", "status": "not_contacted", **kwargs}
    r = client.post("/api/wedding/vendors", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_guest(client, **kwargs):
    payload = {"name": "אורח מנוע", "status": "confirmed", **kwargs}
    r = client.post("/api/wedding/guests", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _set_portions(client, vendor_id, portions):
    r = client.put(f"/api/wedding/vendors/{vendor_id}", json={"portions_ordered": portions})
    assert r.status_code == 200, r.text
    return r.json()


def test_portions_ordered_round_trips(app_client):
    v = _create_vendor(app_client, portions_ordered=120)
    try:
        assert v["portions_ordered"] == 120

        assert _set_portions(app_client, v["id"], 140)["portions_ordered"] == 140
        listed = {x["id"]: x for x in app_client.get("/api/wedding/vendors").json()}
        assert listed[v["id"]]["portions_ordered"] == 140

        # Updating another field leaves the portions alone.
        r = app_client.put(f"/api/wedding/vendors/{v['id']}", json={"name": "קייטרינג אחר"})
        assert r.status_code == 200
        assert r.json()["portions_ordered"] == 140

        # null clears it; negative numbers are rejected.
        assert _set_portions(app_client, v["id"], None)["portions_ordered"] is None
        r = app_client.put(f"/api/wedding/vendors/{v['id']}", json={"portions_ordered": -1})
        assert r.status_code == 422
    finally:
        app_client.delete(f"/api/wedding/vendors/{v['id']}")


def test_vendor_without_portions_defaults_to_null(app_client):
    v = _create_vendor(app_client, category="dj", name="דיג'יי בדיקה")
    try:
        assert v["portions_ordered"] is None
    finally:
        app_client.delete(f"/api/wedding/vendors/{v['id']}")


def test_guests_page_shows_confirmed_headcount(app_client):
    g = _create_guest(app_client)
    try:
        r = app_client.get("/wedding/guests")
        assert r.status_code == 200
        assert "אישרו מתוך" in r.text
    finally:
        app_client.delete(f"/api/wedding/guests/{g['id']}")


def test_catering_card_follows_confirmed_count(app_client, db_conn):
    g = _create_guest(app_client, name="אורח קייטרינג")
    # The highest-priced closed catering deal is the one compared.
    v = _create_vendor(app_client, status="deal_closed", price_quoted=10**9)
    try:
        confirmed = wedding_plan.headcount(db_conn)["confirmed"]
        assert confirmed >= 1

        # No portions recorded yet: nothing to compare.
        assert CATERING_CARD not in app_client.get("/wedding/guests").text

        # More portions than confirmed people.
        _set_portions(app_client, v["id"], confirmed + 5)
        html = app_client.get("/wedding/guests").text
        assert CATERING_CARD in html
        assert '5</bdi> מתחת' in html
        assert f"/wedding/vendors/{v['id']}" in html
        assert f"gcUpdatePortions(this, {v['id']}, {confirmed})" in html

        # Fewer portions than confirmed people.
        _set_portions(app_client, v["id"], confirmed - 1)
        html = app_client.get("/wedding/guests").text
        assert CATERING_CARD in html
        assert '1</bdi> מעל' in html

        # Matching the headcount hides the card.
        _set_portions(app_client, v["id"], confirmed)
        assert CATERING_CARD not in app_client.get("/wedding/guests").text
    finally:
        app_client.delete(f"/api/wedding/vendors/{v['id']}")
        app_client.delete(f"/api/wedding/guests/{g['id']}")


def test_catering_card_ignores_vendor_without_closed_deal(app_client, db_conn):
    g = _create_guest(app_client, name="אורח הצעה")
    v = _create_vendor(app_client, status="quote_received", price_quoted=10**9)
    try:
        confirmed = wedding_plan.headcount(db_conn)["confirmed"]
        _set_portions(app_client, v["id"], confirmed + 3)
        assert f"gcUpdatePortions(this, {v['id']}," not in app_client.get("/wedding/guests").text
    finally:
        app_client.delete(f"/api/wedding/vendors/{v['id']}")
        app_client.delete(f"/api/wedding/guests/{g['id']}")
