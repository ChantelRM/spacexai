"""
End-to-end scenarios from the MVP brief, scripted against the HTTP API.
Grok is faked; everything else is the real stack (DB, services, permissions).
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.factories import FarmerFactory
from apps.ai.tests.helpers import FakeGrok, coordinate_fragments, text_turn, tool_turn
from apps.equipment.models import EquipmentListing
from apps.listings.factories import ProduceListingFactory
from apps.listings.models import ProduceListing
from apps.locations.factories import UserLocationFactory

pytestmark = pytest.mark.django_db
TODAY = date.today()
SOWETO = (Decimal("-26.267800"), Decimal("27.858500"))
PTA = (Decimal("-25.747900"), Decimal("28.229300"))


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def farmer_at(name, town, municipality="City of Johannesburg", gps=None):
    f = FarmerFactory(display_name=name)
    UserLocationFactory(user=f, town=town, municipality=municipality,
                        latitude=gps[0] if gps else None, longitude=gps[1] if gps else None)
    return f


@pytest.fixture
def supply():
    """Farmers with tomatoes and potatoes around Johannesburg, plus one without stock."""
    soweto = farmer_at("Soweto Greens", "Soweto", gps=SOWETO)
    pta = farmer_at("Tshwane Organics", "Pretoria", "City of Tshwane", gps=PTA)
    benoni = farmer_at("Benoni Potatoes", "Benoni", "Ekurhuleni")
    empty = farmer_at("Empty Shelves", "Johannesburg")
    return {
        "tomato_soweto": ProduceListingFactory(farmer=soweto, quantity_available=150, price_per_unit=Decimal("12.00")),
        "potato_soweto": ProduceListingFactory(farmer=soweto, produce_name="Potatoes", quantity_available=60,
                                               price_per_unit=Decimal("8.00")),
        "tomato_pta": ProduceListingFactory(farmer=pta, quantity_available=80, price_per_unit=Decimal("15.00")),
        "potato_benoni": ProduceListingFactory(farmer=benoni, produce_name="Potatoes", quantity_available=500,
                                               price_per_unit=Decimal("7.50")),
        "sold_out": ProduceListingFactory(farmer=empty, quantity_available=0),
        "farmers": [soweto, pta, benoni, empty],
    }


def register(role, email, name):
    c = APIClient()
    res = c.post("/api/v1/auth/register/", {"email": email, "password": "Str0ng-Pass-2026", "role": role,
                                            "display_name": name}, format="json")
    assert res.status_code == 201, res.data
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {res.json()['tokens']['access']}")
    return c


def test_scenario_1_buyer_registers_posts_needs_and_gets_ranked_farmers(supply):
    buyer = register("WHOLESALE_BUYER", "chef@example.com", "Rosebank Bistro")
    assert buyer.put("/api/v1/locations/me/", {"province": "GAUTENG", "municipality": "City of Johannesburg",
                                               "town": "Rosebank", "latitude": -26.1458, "longitude": 28.0419},
                     format="json").status_code == 201
    needed_by = (TODAY + timedelta(days=5)).isoformat()
    for produce, qty in (("Tomatoes", "100"), ("Potatoes", "50")):
        res = buyer.post("/api/v1/buyers/requirements/", {"produce_name": produce, "quantity_needed": qty, "unit": "KG",
                                                          "needed_by": needed_by, "max_distance_km": 50}, format="json")
        assert res.status_code == 201
    body = buyer.get("/api/v1/buyers/me/recommended-farmers/").json()
    items = {i["produce"]: i for i in body["items"]}
    tomatoes = items["Tomatoes"]["results"]
    assert tomatoes[0]["farmer_display_name"] == "Soweto Greens"  # full cover, nearest, cheapest
    assert all(r["farmer_display_name"] != "Empty Shelves" for r in tomatoes)
    # Pretoria is ≈ 48 km from Rosebank by GPS: inside the 50 km limit, but ranked lower (dearer, partial, further).
    assert [r["farmer_display_name"] for r in tomatoes] == ["Soweto Greens", "Tshwane Organics"]
    assert tomatoes[1]["shortfall"] == "Only 80 kg of your 100 kg"
    assert any("covering your 100 kg" in r for r in tomatoes[0]["match_reasons"])
    potatoes = {r["farmer_display_name"]: r for r in items["Potatoes"]["results"]}
    assert potatoes["Soweto Greens"]["shortfall"] is None  # 60 kg covers 50 kg
    assert [e["farmer_display_name"] for e in body["covers_multiple"]] == ["Soweto Greens"]


def test_scenario_2_ai_search_matches_database(supply, buyer, monkeypatch):
    UserLocationFactory(user=buyer, town="Rosebank", latitude=Decimal("-26.145800"), longitude=Decimal("28.041900"))
    monkeypatch.setattr("apps.ai.client.create_response", FakeGrok(
        tool_turn("search_recommended_farmers", produce="tomatoes", quantity=100, unit="KG"),
        text_turn("Soweto Greens is the best match.")))
    body = client_for(buyer).post("/api/v1/ai/chat/", {"message": "Find farmers selling 100 kg of tomatoes near me"},
                                  format="json").json()
    results = body["data"]["search_recommended_farmers"]["results"]
    for r in results:  # every result is a real, active listing with the real price and stock
        listing = ProduceListing.objects.get(pk=r["listing_id"])
        assert listing.status == "ACTIVE" and listing.produce_key == "tomato"
        assert Decimal(str(r["price_per_unit"])) == listing.price_per_unit
        assert Decimal(str(r["available_quantity"])) == listing.quantity_available
        assert r["farmer_id"] == listing.farmer_id
    assert {r["listing_id"] for r in results} == {supply["tomato_soweto"].pk, supply["tomato_pta"].pk}


def test_scenario_3_ai_order_confirm_accept_and_full_lifecycle(supply, buyer, monkeypatch):
    listing = supply["tomato_soweto"]
    farmer = client_for(listing.farmer)
    b = client_for(buyer)
    monkeypatch.setattr("apps.ai.client.create_response", FakeGrok(
        tool_turn("create_order", items=[{"listing_id": listing.pk, "quantity": 100}]), text_turn("Please confirm.")))
    pending = b.post("/api/v1/ai/chat/", {"message": "Order 100 kg tomatoes from Soweto Greens"}, format="json").json()
    assert pending["pending_action"] and b.get("/api/v1/orders/").json()["count"] == 0
    order_id = b.post(f"/api/v1/ai/actions/{pending['pending_action']['id']}/confirm/").json()["result"]["order_id"]

    assert farmer.post(f"/api/v1/orders/{order_id}/accept/").json()["status"] == "ACCEPTED"
    listing.refresh_from_db()
    assert listing.quantity_available == 50  # 150 - 100
    assert farmer.post(f"/api/v1/orders/{order_id}/dispatch/").json()["status"] == "DISPATCHED"
    assert b.post(f"/api/v1/orders/{order_id}/confirm-receipt/").json()["status"] == "DELIVERED"
    assert b.post(f"/api/v1/orders/{order_id}/complete/").json()["status"] == "COMPLETED"


def test_scenario_4_farmer_with_potatoes_sees_buyers_on_dashboard_and_ai(supply, buyer, monkeypatch):
    UserLocationFactory(user=buyer, town="Soweto")
    client_for(buyer).post("/api/v1/buyers/requirements/", {
        "produce_name": "Potatoes", "quantity_needed": "300", "unit": "KG",
        "needed_by": (TODAY + timedelta(days=7)).isoformat()}, format="json")
    farmer = client_for(supply["potato_benoni"].farmer)
    dash = farmer.get("/api/v1/farmers/me/recommended-buyers/").json()
    assert dash["count"] == 1 and dash["results"][0]["buyer_id"] == buyer.pk
    assert any("covering the 300 kg they need" in r for r in dash["results"][0]["match_reasons"])
    monkeypatch.setattr("apps.ai.client.create_response", FakeGrok(
        tool_turn("search_buyer_requirements", produce="potatoes"), text_turn("One buyer needs potatoes.")))
    body = farmer.post("/api/v1/ai/chat/", {"message": "Who needs my potatoes?"}, format="json").json()
    assert body["data"]["search_buyer_requirements"]["results"][0]["requirement_id"] == dash["results"][0]["requirement_id"]


def test_scenario_5_fertiliser_bulk_purchase_5_8_7_10(supply):
    organiser, *others = [farmer_at(f"F{i}", "Soweto") for i in range(4)]
    org = client_for(organiser)
    res = org.post("/api/v1/bulk-purchases/", {
        "item_name": "LAN fertiliser 50 kg", "category": "FERTILISER", "unit": "bag", "unit_price": "450.00",
        "deadline": (TODAY + timedelta(days=5)).isoformat(), "organiser_quantity": "5",
        "discount_tiers": [{"min_total_quantity": "30", "unit_price": "400.00"}]}, format="json")
    assert res.status_code == 201, res.data
    bid = res.json()["id"]
    for f, q in zip(others, ("8", "7", "10")):
        assert client_for(f).post(f"/api/v1/bulk-purchases/{bid}/join/", {"quantity": q}, format="json").status_code == 200
    shares = {s["quantity"]: s["share_amount"] for s in org.get(f"/api/v1/bulk-purchases/{bid}/").json()["breakdown"]["shares"]}
    assert shares == {"5.00": "2000.00", "8.00": "3200.00", "7.00": "2800.00", "10.00": "4000.00"}
    assert org.post(f"/api/v1/bulk-purchases/{bid}/status/", {"status": "LOCKED"}, format="json").status_code == 400
    for f in [organiser] + others:
        client_for(f).post(f"/api/v1/bulk-purchases/{bid}/confirm/")
    assert org.post(f"/api/v1/bulk-purchases/{bid}/status/", {"status": "LOCKED"}, format="json").json()["status"] == "LOCKED"


def test_scenario_6_three_farmers_share_transport_by_weight(supply):
    a, b, c = [farmer_at(n, "Soweto") for n in ("A", "B", "C")]
    res = client_for(a).post("/api/v1/transport/", {
        "pickup_province": "GAUTENG", "pickup_municipality": "City of Johannesburg", "pickup_town": "Soweto",
        "destination": "Joburg Market", "destination_town": "Johannesburg", "destination_province": "GAUTENG",
        "travel_date": (TODAY + timedelta(days=2)).isoformat(), "total_cost": "1800.00", "cost_split_method": "WEIGHT",
        "organiser_load": {"load_weight_kg": "600"}}, format="json")
    tid = res.json()["id"]
    client_for(b).post(f"/api/v1/transport/{tid}/join/", {"load_weight_kg": "300"}, format="json")
    body = client_for(c).post(f"/api/v1/transport/{tid}/join/", {"load_weight_kg": "300"}, format="json").json()
    assert [p["calculated_share"] for p in body["participants"]] == ["900.00", "450.00", "450.00"]


def test_scenario_7_tractor_booking_overlap_rejected(supply):
    owner, renter, other = [farmer_at(n, "Benoni", "Ekurhuleni") for n in ("Owner", "Renter", "Other")]
    tractor = EquipmentListing.objects.create(owner=owner, type="TRACTOR", name="MF 375", rate=Decimal("850"),
                                              rate_unit="PER_DAY")
    start = (timezone.now() + timedelta(days=3)).replace(microsecond=0)
    res = client_for(renter).post(f"/api/v1/equipment/items/{tractor.pk}/book/", {
        "start": start.isoformat(), "end": (start + timedelta(days=2)).isoformat()}, format="json")
    assert res.status_code == 201 and res.json()["estimated_cost"] == "1700.00"
    assert client_for(owner).post(f"/api/v1/equipment/bookings/{res.json()['id']}/decision/", {"approve": True},
                                  format="json").json()["status"] == "APPROVED"
    clash = client_for(other).post(f"/api/v1/equipment/items/{tractor.pk}/book/", {
        "start": (start + timedelta(days=1)).isoformat(), "end": (start + timedelta(days=4)).isoformat()}, format="json")
    assert clash.status_code == 400 and "already booked" in clash.json()["error"]["message"]


def test_scenario_8_buyer_blocked_from_coop_and_coordinates_never_exposed(supply, buyer, monkeypatch):
    b = client_for(buyer)
    UserLocationFactory(user=buyer, town="Rosebank", latitude=Decimal("-26.145800"), longitude=Decimal("28.041900"))
    assert b.get("/api/v1/bulk-purchases/").status_code == 403
    assert b.get("/api/v1/groups/").status_code == 403

    monkeypatch.setattr("apps.ai.client.create_response", FakeGrok(
        tool_turn("find_nearby_farmers"), tool_turn("search_recommended_farmers", produce="tomatoes", quantity=1, unit="KG"),
        text_turn("Done")))
    bodies = [
        b.post("/api/v1/ai/chat/", {"message": "near me"}, format="json").content,
        b.get("/api/v1/marketplace/listings/").content,
        b.get("/api/v1/marketplace/farmers/").content,
        b.get(f"/api/v1/farmers/{supply['farmers'][0].pk}/").content,
        b.get(f"/api/v1/marketplace/listings/{supply['tomato_soweto'].pk}/").content,
        b.post("/api/v1/recommendations/farmers/", {"items": [{"produce": "Tomatoes", "quantity": "1", "unit": "KG"}]},
               format="json").content,
    ]
    for farmer in supply["farmers"]:
        for fragment in coordinate_fragments(farmer.location):
            for body in bodies:
                assert fragment.encode() not in body
