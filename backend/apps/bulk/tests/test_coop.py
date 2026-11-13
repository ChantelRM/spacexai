"""Cooperative features: groups, bulk purchasing, transport, shared services, equipment."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.factories import FarmerFactory
from apps.ai.models import PendingAction
from apps.ai.tests.helpers import FakeGrok, text_turn, tool_turn
from apps.bulk import services as bulk
from apps.bulk.calculations import calculate_cost_shares
from apps.bulk.models import BulkPurchaseMember
from apps.core.costs import allocate
from apps.equipment import services as equipment
from apps.equipment.models import EquipmentListing
from apps.groups import services as groups
from apps.groups.models import GroupMembership
from apps.locations.factories import UserLocationFactory
from apps.services.models import INSURANCE_DISCLAIMER, InsuranceProduct
from apps.transport import services as transport
from apps.transport.models import TransportParticipant

pytestmark = pytest.mark.django_db
D = Decimal
TODAY = date.today()


# --- Cost allocation (pure) ---------------------------------------------------------------

def test_allocate_rounding_sums_exactly():
    assert allocate(D("100"), [1, 1, 1]) == [D("33.34"), D("33.33"), D("33.33")]
    assert allocate(D("10"), [1, 2, 3, 1]) == [D("1.43"), D("2.86"), D("4.28"), D("1.43")]
    assert sum(allocate(D("10"), [1, 2, 3, 1])) == D("10.00")
    assert allocate(D("50"), [0, 0]) == [D("25.00"), D("25.00")]


def test_worked_example_5_8_7_10_bags():
    lines = [{"label": "A", "quantity": 5}, {"label": "B", "quantity": 8}, {"label": "C", "quantity": 7},
             {"label": "D", "quantity": 10}]
    tiers = [{"min_total_quantity": "20", "unit_price": "420"}, {"min_total_quantity": "30", "unit_price": "400"}]
    calc = calculate_cost_shares(lines, D("450"), tiers)
    assert calc["total_quantity"] == 30
    assert calc["applied_tier"] == tiers[1] and calc["unit_price"] == D("400.00")
    assert [s["share_amount"] for s in calc["shares"]] == [D("2000.00"), D("3200.00"), D("2800.00"), D("4000.00")]
    assert calc["total"] == D("12000.00") and calc["savings"] == D("1500.00")
    # 29 bags falls back to the 20+ tier
    assert calculate_cost_shares(lines[:3] + [{"label": "D", "quantity": 9}], D("450"), tiers)["unit_price"] == D("420.00")


def test_shared_fees_split_by_quantity_and_sum_exactly():
    lines = [{"label": "A", "quantity": 5}, {"label": "B", "quantity": 8}, {"label": "C", "quantity": 7},
             {"label": "D", "quantity": 10}]
    calc = calculate_cost_shares(lines, D("400"), shared_fees=D("350"))
    assert [s["fee_amount"] for s in calc["shares"]] == [D("58.33"), D("93.33"), D("81.67"), D("116.67")]
    assert sum(s["share_amount"] for s in calc["shares"]) == calc["total"] == D("12350.00")
    odd = calculate_cost_shares([{"quantity": 1}, {"quantity": 1}, {"quantity": 1}], D("33.33"), shared_fees=D("0.01"))
    assert sum(s["share_amount"] for s in odd["shares"]) == odd["total"] == D("100.00")


def test_equal_method():
    calc = calculate_cost_shares([{"quantity": 1}, {"quantity": 9}], D("10"), method="equal")
    assert [s["share_amount"] for s in calc["shares"]] == [D("50.00"), D("50.00")]


# --- Groups ----------------------------------------------------------------------------

@pytest.fixture
def grp(farmer):
    UserLocationFactory(user=farmer)
    return groups.create_group(farmer, name="Soweto Growers", province="GAUTENG",
                               municipality="City of Johannesburg", town="Soweto", is_open=False, focus="vegetables")


def test_group_join_request_invite_and_admin_rules(farmer, grp):
    a, b = FarmerFactory(), FarmerFactory()
    assert groups.join(a, grp.pk).status == "REQUESTED"  # closed group
    with pytest.raises(PermissionDenied):
        groups.decide_request(a, grp.pk, a.pk, True)  # not an admin
    assert groups.decide_request(farmer, grp.pk, a.pk, True).status == "ACTIVE"
    assert groups.invite(farmer, grp.pk, b.pk).status == "INVITED"
    assert groups.respond_to_invite(b, grp.pk, True).status == "ACTIVE"

    with pytest.raises(ValidationError, match="at least one admin"):
        groups.leave(farmer, grp.pk)  # only admin while others remain
    with pytest.raises(ValidationError):
        groups.set_role(farmer, grp.pk, farmer.pk, "MEMBER")
    groups.set_role(farmer, grp.pk, a.pk, "ADMIN")
    assert groups.leave(farmer, grp.pk).status == "LEFT"
    assert groups.remove_member(a, grp.pk, b.pk).status == "REMOVED"
    with pytest.raises(PermissionDenied):
        groups.join(b, grp.pk)  # removed members can't rejoin by themselves


def test_group_posts_and_announcements(farmer, grp):
    member = FarmerFactory()
    groups.invite(farmer, grp.pk, member.pk)
    groups.respond_to_invite(member, grp.pk, True)
    with pytest.raises(PermissionDenied):
        groups.create_post(member, grp.pk, "Hello", is_announcement=True)
    groups.create_post(member, grp.pk, "Hello all")
    groups.create_post(farmer, grp.pk, "Meeting Friday", is_announcement=True)
    assert [p.is_announcement for p in groups.list_posts(member, grp.pk)] == [True, False]
    with pytest.raises(PermissionDenied):
        groups.list_posts(FarmerFactory(), grp.pk)


def test_group_api_and_search(farmer_client, farmer, grp):
    res = farmer_client.get("/api/v1/groups/", {"focus": "vegetables"})
    assert [g["name"] for g in res.json()["results"]] == ["Soweto Growers"]
    assert res.json()["results"][0]["my_status"] == "ACTIVE"
    res = farmer_client.post("/api/v1/groups/", {"name": "Open Poultry", "group_type": "PRODUCE", "province": "GAUTENG",
                                                 "municipality": "Ekurhuleni", "focus": "poultry"}, format="json")
    assert res.status_code == 201
    assert farmer_client.get(f"/api/v1/groups/{grp.pk}/").json()["members"][0]["role"] == "ADMIN"


# --- Bulk purchasing -----------------------------------------------------------------------

@pytest.fixture
def fertiliser(farmer):
    return bulk.create_purchase(farmer, item_name="LAN fertiliser 50 kg", category="FERTILISER", unit="bag",
                                unit_price=D("450"), deadline=TODAY + timedelta(days=7), organiser_quantity=D("5"),
                                discount_tiers=[{"min_total_quantity": "20", "unit_price": "420"},
                                                {"min_total_quantity": "30", "unit_price": "400"}])


def contributions(bp):
    return {m.farmer_id: m.calculated_contribution for m in BulkPurchaseMember.objects.filter(bulk_purchase=bp)}


def test_bulk_join_recalculates_and_lock_needs_all_confirmations(farmer, fertiliser):
    others = [FarmerFactory() for _ in range(3)]
    assert contributions(fertiliser)[farmer.pk] == D("2250.00")  # 5 × R450 alone
    bulk.confirm(farmer, fertiliser.pk)
    for f, q in zip(others, (8, 7, 10)):
        bulk.join(f, fertiliser.pk, q)
    c = contributions(fertiliser)
    assert [c[farmer.pk]] + [c[f.pk] for f in others] == [D("2000.00"), D("3200.00"), D("2800.00"), D("4000.00")]
    # The organiser's amount changed, so their earlier confirmation was reset.
    assert not BulkPurchaseMember.objects.get(bulk_purchase=fertiliser, farmer=farmer).confirmed

    with pytest.raises(ValidationError, match="haven't confirmed"):
        bulk.set_status(farmer, fertiliser.pk, "LOCKED")
    for f in [farmer] + others:
        bulk.confirm(f, fertiliser.pk)
    with pytest.raises(PermissionDenied):
        bulk.set_status(others[0], fertiliser.pk, "LOCKED")
    assert bulk.set_status(farmer, fertiliser.pk, "LOCKED").status == "LOCKED"
    with pytest.raises(ValidationError):
        bulk.join(FarmerFactory(), fertiliser.pk, 1)


def test_bulk_leave_recalculates(farmer, fertiliser):
    other = FarmerFactory()
    bulk.join(other, fertiliser.pk, 25)  # 30 total -> R400
    assert contributions(fertiliser)[farmer.pk] == D("2000.00")
    bulk.leave(other, fertiliser.pk)
    assert contributions(fertiliser)[farmer.pk] == D("2250.00")


def test_bulk_api_breakdown(farmer_client, fertiliser):
    body = farmer_client.get(f"/api/v1/bulk-purchases/{fertiliser.pk}/").json()
    assert body["breakdown"]["total"] == "2250.00"
    res = farmer_client.post("/api/v1/bulk-purchases/calculator/", {
        "unit_price": "450", "lines": [{"label": "A", "quantity": "5"}, {"label": "B", "quantity": "8"},
                                       {"label": "C", "quantity": "7"}, {"label": "D", "quantity": "10"}],
        "discount_tiers": [{"min_total_quantity": "30", "unit_price": "400"}]}, format="json")
    assert res.status_code == 200 and res.json()["total"] == "12000.00"


# --- Transport ------------------------------------------------------------------------------

@pytest.fixture
def trip(farmer):
    UserLocationFactory(user=farmer, town="Soweto")
    return transport.create_request(farmer, pickup_province="GAUTENG", pickup_municipality="City of Johannesburg",
                                     pickup_town="Soweto", destination="Joburg Market", destination_town="Johannesburg",
                                     destination_municipality="City of Johannesburg", destination_province="GAUTENG",
                                     travel_date=TODAY + timedelta(days=3), total_cost=D("1500"),
                                     cost_split_method="WEIGHT", capacity=D("2000"), capacity_unit="KG",
                                     organiser_load={"load_weight_kg": D("500")})


def shares(tr):
    return [p.calculated_share for p in TransportParticipant.objects.filter(request=tr).order_by("id")]


def test_transport_weight_split_and_capacity(farmer, trip):
    a, b = FarmerFactory(), FarmerFactory()
    transport.join(a, trip.pk, load_weight_kg=D("300"))
    transport.join(b, trip.pk, load_weight_kg=D("200"))
    assert shares(trip) == [D("750.00"), D("450.00"), D("300.00")]
    with pytest.raises(ValidationError, match="Needed"):
        transport.join(FarmerFactory(), trip.pk)  # weight required for WEIGHT split
    with pytest.raises(ValidationError, match="space"):
        transport.join(FarmerFactory(), trip.pk, load_weight_kg=D("1500"))  # over 2000 kg


@pytest.mark.parametrize("method,expected", [
    ("EQUAL", [D("500.00"), D("500.00"), D("500.00")]),
    ("VOLUME", [D("750.00"), D("500.00"), D("250.00")]),
    ("SPACE", [D("500.00"), D("500.00"), D("500.00")]),
])
def test_transport_other_splits(farmer, trip, method, expected):
    TransportParticipant.objects.filter(request=trip).update(load_volume_m3=D("3"), load_space_units=D("1"))
    a, b = FarmerFactory(), FarmerFactory()
    transport.join(a, trip.pk, load_weight_kg=D("1"), load_volume_m3=D("2"), load_space_units=D("1"))
    transport.join(b, trip.pk, load_weight_kg=D("1"), load_volume_m3=D("1"), load_space_units=D("1"))
    transport.update_cost(farmer, trip.pk, cost_split_method=method)
    assert shares(trip) == expected


def test_transport_distance_split_uses_tiers_without_gps(farmer, trip):
    near = FarmerFactory()
    UserLocationFactory(user=near, town="Johannesburg")  # same town as destination: 5 km tier
    transport.join(near, trip.pk, load_weight_kg=D("1"))
    transport.update_cost(farmer, trip.pk, cost_split_method="DISTANCE")
    # organiser in Soweto (same municipality: 30 km) vs 5 km -> 30:5
    assert shares(trip) == [D("1285.71"), D("214.29")]


def test_transport_agreed_amounts_must_sum(farmer, trip):
    other = FarmerFactory()
    transport.update_cost(farmer, trip.pk, cost_split_method="AGREED")
    TransportParticipant.objects.filter(request=trip, farmer=farmer).update(agreed_amount=D("1000"))
    transport.join(other, trip.pk, load_weight_kg=D("1"), agreed_amount=D("400"))
    assert shares(trip) == [None, None]
    assert "add up to R1400.00" in transport.compute_shares(transport.get_request(trip.pk))["problem"]
    with pytest.raises(ValidationError):
        transport.confirm(other, trip.pk)
    transport.join(other, trip.pk, load_weight_kg=D("1"), agreed_amount=D("500"))
    assert shares(trip) == [D("1000.00"), D("500.00")]


def test_transport_confirm_flow_and_ranking(farmer, trip, auth_client):
    other = FarmerFactory()
    transport.join(other, trip.pk, load_weight_kg=D("500"))
    with pytest.raises(ValidationError):
        transport.set_status(farmer, trip.pk, "CONFIRMED")
    transport.confirm(farmer, trip.pk)
    transport.confirm(other, trip.pk)
    assert transport.set_status(farmer, trip.pk, "CONFIRMED").status == "CONFIRMED"
    seeker = FarmerFactory()
    UserLocationFactory(user=seeker, town="Soweto")
    assert transport.find_transport_requests(seeker)["count"] == 0  # confirmed trips are not open


# --- Shared services & insurance -------------------------------------------------------------------

def test_security_cost_sharing_and_alerts(farmer_client, farmer, auth_client):
    UserLocationFactory(user=farmer)
    res = farmer_client.post("/api/v1/services/security/", {
        "title": "Night patrol", "province": "GAUTENG", "municipality": "City of Johannesburg",
        "total_monthly_cost": "3000"}, format="json")
    assert res.status_code == 201
    sid = res.json()["id"]
    other = auth_client(FarmerFactory())
    other.post(f"/api/v1/services/security/{sid}/join/", {}, format="json")
    body = farmer_client.get(f"/api/v1/services/security/{sid}/").json()
    assert [c["amount"] for c in body["contributions"]] == ["1500.00", "1500.00"]

    bad = farmer_client.post("/api/v1/services/security-alerts/", {
        "alert_type": "THEFT", "title": "Stolen pump", "body": "Suspect ID 8001015009087 seen",
        "province": "GAUTENG", "municipality": "City of Johannesburg"}, format="json")
    assert bad.status_code == 400
    ok = farmer_client.post("/api/v1/services/security-alerts/", {
        "alert_type": "THEFT", "title": "Stolen pump", "body": "Irrigation pump taken near the dam on Tuesday night.",
        "province": "GAUTENG", "municipality": "City of Johannesburg"}, format="json")
    assert ok.status_code == 201
    assert farmer_client.get("/api/v1/services/security-alerts/").json()["count"] == 1


def test_insurance_always_has_disclaimer(farmer_client):
    InsuranceProduct.objects.create(provider_name="Agri Cover Co", name="Crop hail", category="CROP",
                                    summary="Hail cover for crops", is_authorised_provider=True)
    res = farmer_client.get("/api/v1/services/insurance/products/")
    assert res.json()["disclaimer"] == INSURANCE_DISCLAIMER and len(res.json()["results"]) == 1
    res = farmer_client.post("/api/v1/services/insurance/quote-requests/", {
        "category": "CROP", "details": "5 ha maize"}, format="json")
    assert res.status_code == 201 and res.json()["disclaimer"] == INSURANCE_DISCLAIMER
    assert farmer_client.get("/api/v1/services/insurance/quote-requests/").json()["disclaimer"]


# --- Equipment ----------------------------------------------------------------------------

@pytest.fixture
def tractor(farmer):
    return EquipmentListing.objects.create(owner=farmer, type="TRACTOR", name="Massey 375", rate=D("800"),
                                           rate_unit="PER_DAY")


def at(days, hour=8):
    return timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)


def test_equipment_overlap_rejected(farmer, tractor):
    a, b = FarmerFactory(), FarmerFactory()
    first = equipment.request_booking(a, equipment_id=tractor.pk, start=at(2), end=at(4))
    assert first.estimated_cost == D("1600.00")
    second = equipment.request_booking(b, equipment_id=tractor.pk, start=at(3), end=at(5))  # requests may overlap
    equipment.decide(farmer, first.pk, True)
    with pytest.raises(ValidationError, match="already booked"):
        equipment.decide(farmer, second.pk, True)
    with pytest.raises(ValidationError, match="already booked"):
        equipment.request_booking(FarmerFactory(), equipment_id=tractor.pk, start=at(3), end=at(3, 12))
    assert equipment.request_booking(b, equipment_id=tractor.pk, start=at(4), end=at(6)).status == "REQUESTED"
    with pytest.raises(ValidationError):
        equipment.request_booking(farmer, equipment_id=tractor.pk, start=at(10), end=at(11))  # own equipment
    with pytest.raises(Exception):
        equipment.decide(a, first.pk, False)  # only the owner decides


def test_storage_capacity(farmer):
    cold = EquipmentListing.objects.create(owner=farmer, type="COLD_STORAGE", name="Cold room", rate=D("15"),
                                           rate_unit="PER_TONNE_PER_DAY", capacity=D("10"))
    a, b, c = FarmerFactory(), FarmerFactory(), FarmerFactory()
    ba = equipment.request_booking(a, equipment_id=cold.pk, start=at(1), end=at(3), quantity=D("6"))
    assert ba.estimated_cost == D("180.00")  # 6 t × 2 days × R15
    bb = equipment.request_booking(b, equipment_id=cold.pk, start=at(2), end=at(4), quantity=D("4"))
    equipment.decide(farmer, ba.pk, True)
    equipment.decide(farmer, bb.pk, True)  # 6 + 4 = 10: fits
    with pytest.raises(ValidationError, match="Only 0"):
        equipment.request_booking(c, equipment_id=cold.pk, start=at(2), end=at(3), quantity=D("1"))


# --- Buyers are blocked everywhere ---------------------------------------------------------------

@pytest.mark.parametrize("method,url", [
    ("get", "/api/v1/groups/"), ("post", "/api/v1/groups/"), ("get", "/api/v1/groups/1/"),
    ("post", "/api/v1/groups/1/join/"), ("get", "/api/v1/bulk-purchases/"), ("post", "/api/v1/bulk-purchases/"),
    ("post", "/api/v1/bulk-purchases/1/join/"), ("post", "/api/v1/bulk-purchases/calculator/"),
    ("get", "/api/v1/transport/"), ("post", "/api/v1/transport/1/join/"), ("get", "/api/v1/services/security/"),
    ("get", "/api/v1/services/security-alerts/"), ("get", "/api/v1/services/insurance/products/"),
    ("post", "/api/v1/services/insurance/quote-requests/"), ("get", "/api/v1/equipment/items/"),
    ("post", "/api/v1/equipment/items/1/book/"), ("get", "/api/v1/equipment/bookings/"),
])
def test_buyers_blocked_from_coop_endpoints(buyer_client, method, url):
    res = getattr(buyer_client, method)(url, {}, format="json")
    assert res.status_code == 403, url
    assert res.json()["error"]["code"] == "permission_denied"


# --- AI commitment tools all need confirmation ----------------------------------------------------

def run_ai(client, monkeypatch, name, **args):
    monkeypatch.setattr("apps.ai.client.create_response", FakeGrok(tool_turn(name, **args), text_turn("Confirm?")))
    body = client.post("/api/v1/ai/chat/", {"message": "do it"}, format="json").json()
    return body


def confirm_ai(client, body):
    return client.post(f"/api/v1/ai/actions/{body['pending_action']['id']}/confirm/")


def test_ai_bulk_join_and_confirm_need_confirmation(auth_client, fertiliser, monkeypatch):
    joiner = FarmerFactory()
    client = auth_client(joiner)
    body = run_ai(client, monkeypatch, "join_bulk_purchase", bulk_purchase_id=fertiliser.pk, quantity=25)
    assert "Estimated contribution R10 000.00 at R400.00/bag for 30 bag in total" in body["pending_action"]["summary"]
    assert not BulkPurchaseMember.objects.filter(farmer=joiner).exists()
    assert confirm_ai(client, body).status_code == 200
    assert BulkPurchaseMember.objects.get(farmer=joiner).quantity == 25

    body = run_ai(client, monkeypatch, "confirm_bulk_purchase_contribution", bulk_purchase_id=fertiliser.pk)
    assert "commitment to pay" in body["pending_action"]["summary"]
    assert not BulkPurchaseMember.objects.get(farmer=joiner).confirmed
    confirm_ai(client, body)
    assert BulkPurchaseMember.objects.get(farmer=joiner).confirmed


def test_ai_transport_join_needs_confirmation(auth_client, trip, monkeypatch):
    joiner = FarmerFactory()
    client = auth_client(joiner)
    body = run_ai(client, monkeypatch, "join_transport_request", transport_request_id=trip.pk, load_weight_kg=250)
    assert body["pending_action"]["summary"].startswith("Join the shared trip to Joburg Market")
    assert not TransportParticipant.objects.filter(farmer=joiner).exists()
    confirm_ai(client, body)
    assert TransportParticipant.objects.get(farmer=joiner).calculated_share is not None


def test_ai_equipment_booking_needs_confirmation(auth_client, tractor, monkeypatch):
    client = auth_client(FarmerFactory())
    start = (TODAY + timedelta(days=5)).isoformat()
    end = (TODAY + timedelta(days=6)).isoformat()
    body = run_ai(client, monkeypatch, "request_equipment_booking", equipment_id=tractor.pk, start_date=start,
                  end_date=end)
    assert "Estimated cost R1 600.00" in body["pending_action"]["summary"]
    assert tractor.bookings.count() == 0
    assert confirm_ai(client, body).status_code == 200
    assert tractor.bookings.get().status == "REQUESTED"


def test_ai_tool_with_missing_object_is_invalid_not_404(farmer_client, monkeypatch):
    body = run_ai(farmer_client, monkeypatch, "join_bulk_purchase", bulk_purchase_id=99999, quantity=1)
    assert body["tool_calls"] == [{"name": "join_bulk_purchase", "status": "invalid"}]
    assert PendingAction.objects.count() == 0


def test_find_nearby_farmers_by_produce(farmer, auth_client):
    from apps.farmers.models import FarmerProfile
    from apps.listings.factories import ProduceListingFactory

    UserLocationFactory(user=farmer)
    tomato, poultry = FarmerFactory(display_name="Tomato T"), FarmerFactory(display_name="Chicken C")
    UserLocationFactory(user=tomato)
    UserLocationFactory(user=poultry)
    ProduceListingFactory(farmer=tomato)
    FarmerProfile.objects.create(user=poultry, farm_name="Hens", main_produce=["Eggs"])
    from apps.ai.tools.registry import execute_tool_call

    names = [r["display_name"] for r in execute_tool_call(farmer, "find_nearby_farmers",
                                                         '{"produce": "tomatoes"}').result["results"]]
    assert names == ["Tomato T"]
    names = [r["display_name"] for r in execute_tool_call(farmer, "find_nearby_farmers",
                                                         '{"produce": "eggs"}').result["results"]]
    assert names == ["Chicken C"]


def test_membership_model_unique(farmer, grp):
    assert GroupMembership.objects.filter(group=grp, farmer=farmer).count() == 1
