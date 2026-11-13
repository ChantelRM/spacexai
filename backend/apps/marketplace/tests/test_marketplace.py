from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.accounts.factories import BuyerFactory, FarmerFactory
from apps.ai.tests.helpers import coordinate_fragments
from apps.buyers.models import BuyerRequirement
from apps.farmers.models import FarmerProfile
from apps.listings.factories import ProduceListingFactory
from apps.locations.factories import UserLocationFactory
from apps.locations.models import Province
from apps.messaging.models import Conversation

pytestmark = pytest.mark.django_db

SEARCH = "/api/v1/marketplace/listings/"
JHB = (Decimal("-26.204100"), Decimal("28.047300"))
SOWETO = (Decimal("-26.267800"), Decimal("27.858500"))


@pytest.fixture
def setup(buyer):
    UserLocationFactory(user=buyer, latitude=JHB[0], longitude=JHB[1])
    soweto = FarmerFactory(display_name="Soweto Greens")
    UserLocationFactory(user=soweto, town="Soweto", latitude=SOWETO[0], longitude=SOWETO[1], address_line="Hidden 1")
    FarmerProfile.objects.create(user=soweto, farm_name="SG Farm", is_verified=True, main_produce=["Spinach"])
    limpopo = FarmerFactory(display_name="Limpopo Roots")
    UserLocationFactory(user=limpopo, province=Province.LIMPOPO, municipality="Polokwane", town="Polokwane")
    return {
        "tomato_soweto": ProduceListingFactory(farmer=soweto, price_per_unit=14, quantity_available=50,
                                               category_id=1),
        "tomato_limpopo": ProduceListingFactory(farmer=limpopo, price_per_unit=9, unit="TONNE",
                                                quantity_available=Decimal("2"), quality_grade="PREMIUM"),
        "potato": ProduceListingFactory(farmer=limpopo, produce_name="Potatoes", price_per_unit=6,
                                        available_from=date.today() + timedelta(days=10)),
        "paused": ProduceListingFactory(farmer=soweto, status="PAUSED"),
    }


def ids(res):
    return [r["id"] for r in res.json()["results"]]


def test_search_filters(buyer_client, setup):
    s = setup
    assert set(ids(buyer_client.get(SEARCH))) == {s["tomato_soweto"].pk, s["tomato_limpopo"].pk, s["potato"].pk}
    assert set(ids(buyer_client.get(SEARCH, {"q": "tomato"}))) == {s["tomato_soweto"].pk, s["tomato_limpopo"].pk}
    assert ids(buyer_client.get(SEARCH, {"q": "tomatoes", "max_price": "10"})) == [s["tomato_limpopo"].pk]
    assert ids(buyer_client.get(SEARCH, {"q": "tomatoes", "min_price": "10"})) == [s["tomato_soweto"].pk]
    # Unit-aware: 2 tonnes = 2000 kg >= 500 kg; 50 kg is not.
    assert ids(buyer_client.get(SEARCH, {"min_quantity": "500", "unit": "KG"})) == [s["tomato_limpopo"].pk]
    assert ids(buyer_client.get(SEARCH, {"quality_grade": "PREMIUM"})) == [s["tomato_limpopo"].pk]
    assert set(ids(buyer_client.get(SEARCH, {"province": "LIMPOPO"}))) == {s["tomato_limpopo"].pk, s["potato"].pk}
    assert ids(buyer_client.get(SEARCH, {"town": "soweto"})) == [s["tomato_soweto"].pk]
    assert ids(buyer_client.get(SEARCH, {"max_distance_km": "50"})) == [s["tomato_soweto"].pk]
    assert s["potato"].pk not in ids(buyer_client.get(SEARCH, {"available_by": date.today().isoformat()}))
    assert buyer_client.get(SEARCH, {"sort": "bogus"}).status_code == 400
    assert buyer_client.get(SEARCH, {"province": "ATLANTIS"}).status_code == 400


def test_search_sorting_and_pagination(buyer_client, setup):
    s = setup
    assert ids(buyer_client.get(SEARCH, {"sort": "price"}))[0] == s["potato"].pk
    assert ids(buyer_client.get(SEARCH, {"sort": "-price"}))[0] == s["tomato_soweto"].pk
    assert ids(buyer_client.get(SEARCH, {"sort": "distance"}))[0] == s["tomato_soweto"].pk
    assert ids(buyer_client.get(SEARCH, {"sort": "-quantity"}))[0] == s["tomato_limpopo"].pk
    res = buyer_client.get(SEARCH, {"page_size": 2})
    assert res.json()["count"] == 3 and len(res.json()["results"]) == 2 and res.json()["next"]


def test_listing_payload_is_privacy_safe(buyer_client, setup):
    res = buyer_client.get(f"/api/v1/marketplace/listings/{setup['tomato_soweto'].pk}/")
    body = res.json()
    assert body["farmer"] == {"id": setup["tomato_soweto"].farmer_id, "display_name": "Soweto Greens",
                              "farm_name": "SG Farm", "is_verified": True}
    assert body["location"]["distance"]["basis"] == "gps"
    text = res.content.decode()
    for fragment in coordinate_fragments(setup["tomato_soweto"].farmer.location):
        assert fragment not in text
    assert "Hidden" not in text and setup["tomato_soweto"].farmer.email not in text
    assert buyer_client.get(f"/api/v1/marketplace/listings/{setup['paused'].pk}/").status_code == 404


def test_compare(buyer_client, setup):
    s = setup
    res = buyer_client.get("/api/v1/marketplace/compare/",
                           {"listing_ids": f"{s['tomato_soweto'].pk},{s['tomato_limpopo'].pk},{s['paused'].pk}"})
    body = res.json()
    assert body["count"] == 2 and body["unavailable_listing_ids"] == [s["paused"].pk]
    assert body["nearest_listing_id"] == s["tomato_soweto"].pk
    assert body["results"][0]["reliability"]["note"]
    assert buyer_client.get("/api/v1/marketplace/compare/", {"listing_ids": "1"}).status_code == 400


def test_farmer_discovery(buyer_client, setup):
    res = buyer_client.get("/api/v1/marketplace/farmers/")
    assert [f["display_name"] for f in res.json()["results"]] == ["Soweto Greens", "Limpopo Roots"]
    res = buyer_client.get("/api/v1/marketplace/farmers/", {"produce": "spinach"})  # from profile main_produce
    assert [f["display_name"] for f in res.json()["results"]] == ["Soweto Greens"]
    res = buyer_client.get("/api/v1/marketplace/farmers/", {"produce": "potatoes", "verified": "true"})
    assert res.json()["count"] == 0


# --- Buyers ----------------------------------------------------------------------------

def test_buyer_profile_and_requirements(buyer_client, farmer_client):
    res = buyer_client.put("/api/v1/buyers/me/profile/", {"business_name": "Rosebank Bistro",
                                                          "business_type": "RESTAURANT"}, format="json")
    assert res.status_code == 201
    assert farmer_client.get("/api/v1/buyers/me/profile/").status_code == 403

    url = "/api/v1/buyers/requirements/"
    payload = {"produce_name": "Tomatoes", "quantity_needed": "100", "unit": "KG",
               "needed_by": (date.today() + timedelta(days=5)).isoformat(), "max_distance_km": 50}
    res = buyer_client.post(url, payload, format="json")
    assert res.status_code == 201, res.data
    rid = res.json()["id"]
    assert res.json()["produce_key"] == "tomato" and res.json()["status"] == "OPEN"
    assert buyer_client.patch(f"{url}{rid}/", {"quantity_needed": "120"}, format="json").status_code == 200
    past = {**payload, "needed_by": (date.today() - timedelta(days=1)).isoformat()}
    assert buyer_client.post(url, past, format="json").status_code == 400
    assert buyer_client.post(url, {**payload, "quantity_needed": "0"}, format="json").status_code == 400
    assert farmer_client.post(url, payload, format="json").status_code == 403
    assert buyer_client.delete(f"{url}{rid}/").status_code == 204
    assert BuyerRequirement.objects.get(pk=rid).status == "CLOSED"


def test_requirements_are_private_to_owner(buyer_client, auth_client):
    rid = buyer_client.post("/api/v1/buyers/requirements/", {
        "produce_name": "Beans", "quantity_needed": "5", "unit": "KG",
        "needed_by": (date.today() + timedelta(days=3)).isoformat()}, format="json").json()["id"]
    other = auth_client(BuyerFactory())
    assert other.get(f"/api/v1/buyers/requirements/{rid}/").status_code == 404


def test_public_buyer_profile(farmer_client, buyer):
    res = farmer_client.get(f"/api/v1/buyers/{buyer.pk}/")
    assert res.status_code == 200 and buyer.email not in res.content.decode()


# --- Messaging -------------------------------------------------------------------------

def test_messaging_participants_only(buyer_client, buyer, farmer, farmer_client, auth_client):
    res = buyer_client.post("/api/v1/messaging/conversations/", {"other_user_id": farmer.pk,
                                                                "message": "Hi, do you have tomatoes?"}, format="json")
    assert res.status_code == 201, res.data
    cid = res.json()["id"]
    assert res.json()["other_party"]["display_name"] == farmer.display_name
    # Reusing the thread instead of duplicating it.
    again = buyer_client.post("/api/v1/messaging/conversations/", {"other_user_id": farmer.pk}, format="json")
    assert again.json()["id"] == cid and Conversation.objects.count() == 1

    inbox = farmer_client.get("/api/v1/messaging/conversations/").json()
    assert inbox["results"][0]["unread_count"] == 1
    assert farmer_client.post(f"/api/v1/messaging/conversations/{cid}/messages/", {"body": "Yes, 100 kg"},
                              format="json").status_code == 201
    assert farmer_client.post(f"/api/v1/messaging/conversations/{cid}/read/").json() == {"marked_read": 1}
    msgs = buyer_client.get(f"/api/v1/messaging/conversations/{cid}/messages/").json()["results"]
    assert [m["body"] for m in msgs] == ["Hi, do you have tomatoes?", "Yes, 100 kg"]

    outsider = auth_client(FarmerFactory())
    assert outsider.get(f"/api/v1/messaging/conversations/{cid}/messages/").status_code == 404
    assert outsider.post(f"/api/v1/messaging/conversations/{cid}/messages/", {"body": "x"},
                         format="json").status_code == 404


def test_messaging_requires_buyer_and_farmer(farmer_client, auth_client):
    other_farmer = FarmerFactory()
    res = farmer_client.post("/api/v1/messaging/conversations/", {"other_user_id": other_farmer.pk}, format="json")
    assert res.status_code == 400
