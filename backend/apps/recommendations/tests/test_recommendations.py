from datetime import date, timedelta
from decimal import Decimal

import pytest

from apps.accounts.factories import BuyerFactory, FarmerFactory
from apps.ai.tests.helpers import coordinate_fragments
from apps.buyers.factories import BuyerRequirementFactory
from apps.listings.factories import ProduceListingFactory
from apps.locations.factories import UserLocationFactory
from apps.locations.models import Province
from apps.recommendations import services
from apps.recommendations.models import RecommendationLog

pytestmark = pytest.mark.django_db

JHB = (Decimal("-26.204100"), Decimal("28.047300"))
SOWETO = (Decimal("-26.267800"), Decimal("27.858500"))
PTA = (Decimal("-25.747900"), Decimal("28.229300"))


def farmer_at(name, town="Johannesburg", municipality="City of Johannesburg", province=Province.GAUTENG, gps=None):
    f = FarmerFactory(display_name=name)
    UserLocationFactory(user=f, town=town, municipality=municipality, province=province,
                        latitude=gps[0] if gps else None, longitude=gps[1] if gps else None)
    return f


@pytest.fixture
def buyer_jhb(db):
    b = BuyerFactory(display_name="Rosebank Bistro")
    UserLocationFactory(user=b, latitude=JHB[0], longitude=JHB[1])
    return b


@pytest.fixture
def market(buyer_jhb):
    """Four tomato sellers with different strengths, plus noise that must never match."""
    near_full = farmer_at("Near Full", town="Soweto", gps=SOWETO)
    far_cheap = farmer_at("Far Cheap", province=Province.LIMPOPO, municipality="Polokwane", town="Polokwane")
    partial = farmer_at("Partial Stock", gps=JHB)
    pretoria = farmer_at("Pretoria Premium", municipality="City of Tshwane", town="Pretoria", gps=PTA)
    listings = {
        "near_full": ProduceListingFactory(farmer=near_full, quantity_available=150, price_per_unit=12),
        "far_cheap": ProduceListingFactory(farmer=far_cheap, quantity_available=500, price_per_unit=8),
        "partial": ProduceListingFactory(farmer=partial, quantity_available=60, price_per_unit=11),
        "pretoria": ProduceListingFactory(farmer=pretoria, quantity_available=Decimal("0.2"), unit="TONNE",
                                          price_per_unit=15000, quality_grade="PREMIUM"),
    }
    # Noise: wrong produce, sold out, paused, deleted.
    noise = farmer_at("Noise Farm", gps=JHB)
    ProduceListingFactory(farmer=noise, produce_name="Potatoes")
    ProduceListingFactory(farmer=noise, quantity_available=0)
    ProduceListingFactory(farmer=noise, status="PAUSED")
    ProduceListingFactory(farmer=noise, status="DELETED")
    return listings


def names(result):
    return [r["farmer_display_name"] for r in result["results"]]


def test_ranking_reasons_and_shortfall(buyer_jhb, market):
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG",
                                                 needed_by=date.today() + timedelta(days=5))
    assert set(names(result)) == {"Near Full", "Far Cheap", "Partial Stock", "Pretoria Premium"}
    top = result["results"][0]
    assert top["farmer_display_name"] == "Near Full"
    assert top["shortfall"] is None
    assert any("covering your 100 kg" in r for r in top["match_reasons"])
    assert any(r.startswith("≈") and r.endswith("km away") for r in top["match_reasons"])
    assert any("New on the platform" in r for r in top["match_reasons"])

    partial = next(r for r in result["results"] if r["farmer_display_name"] == "Partial Stock")
    assert partial["shortfall"] == "Only 60 kg of your 100 kg"
    # Tonne listing converted: 0.2 tonne = 200 kg covers 100 kg; R15 000/tonne = R15/kg
    pta = next(r for r in result["results"] if r["farmer_display_name"] == "Pretoria Premium")
    assert pta["shortfall"] is None
    assert any("R15.00/kg" in r for r in pta["match_reasons"])
    assert all(0 <= r["score"] <= 100 for r in result["results"])
    assert [r["score"] for r in result["results"]] == sorted((r["score"] for r in result["results"]), reverse=True)


def test_never_returns_farmers_without_the_produce(buyer_jhb, market):
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=10, unit="KG")
    assert "Noise Farm" not in names(result)
    assert services.search_recommended_farmers(buyer_jhb, produce="avocados", quantity=10, unit="KG")["count"] == 0


def test_hard_filters_distance_with_and_without_gps(buyer_jhb, market):
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG",
                                                 max_distance_km=30)
    assert set(names(result)) == {"Near Full", "Partial Stock"}  # Pretoria ≈55 km GPS; Limpopo tier 600 km
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG",
                                                 max_distance_km=60)
    assert "Pretoria Premium" in names(result) and "Far Cheap" not in names(result)


def test_future_stock_only_counts_when_ready_in_time(buyer_jhb, market):
    later = farmer_at("Later Farm", gps=JHB)
    ProduceListingFactory(farmer=later, available_from=date.today() + timedelta(days=30))
    soon = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG",
                                               needed_by=date.today() + timedelta(days=5))
    assert "Later Farm" not in names(soon)
    anytime = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG")
    later_match = next(r for r in anytime["results"] if r["farmer_display_name"] == "Later Farm")
    assert any(r.startswith("Available from") for r in later_match["match_reasons"])


def test_needed_by_and_incompatible_units(buyer_jhb, market):
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=5, unit="CRATE")
    assert result["count"] == 0  # KG/TONNE listings can't satisfy crates


def test_max_price_and_min_quality_are_explained(buyer_jhb, market):
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG",
                                                 max_price=Decimal("12"), min_quality="PREMIUM")
    pta = next(r for r in result["results"] if r["farmer_display_name"] == "Pretoria Premium")
    assert any("above the maximum" in g for g in pta["gaps"])
    near = next(r for r in result["results"] if r["farmer_display_name"] == "Near Full")
    assert any("below the minimum Premium" in g for g in near["gaps"])


def test_requirement_criteria_and_logging(buyer_jhb, market):
    req = BuyerRequirementFactory(buyer=buyer_jhb, max_distance_km=30)
    result = services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=100, unit="KG",
                                                 requirement_id=req.pk, source="api")
    assert set(names(result)) == {"Near Full", "Partial Stock"}
    log = RecommendationLog.objects.get()
    assert log.direction == "BUYER_TO_FARMER" and log.source == "api"
    assert [r["id"] for r in log.results] == [r["listing_id"] for r in result["results"]]


def test_multi_item_covers_multiple(buyer_jhb, market):
    near = market["near_full"].farmer
    ProduceListingFactory(farmer=near, produce_name="Potatoes", quantity_available=80)
    result = services.recommend_farmers_for_items(buyer_jhb, [
        {"produce": "Tomatoes", "quantity": 100, "unit": "KG"},
        {"produce": "Potatoes", "quantity": 50, "unit": "KG"},
    ])
    assert [i["produce"] for i in result["items"]] == ["Tomatoes", "Potatoes"]
    assert [e["farmer_display_name"] for e in result["covers_multiple"]] == ["Near Full"]
    potato_matches = {r["farmer_display_name"]: r for r in result["items"][1]["results"]}
    assert potato_matches["Near Full"]["covers_multiple"] is True
    assert potato_matches["Noise Farm"]["covers_multiple"] is False


def test_results_never_contain_coordinates(buyer_jhb, market):
    import json

    blob = json.dumps(services.search_recommended_farmers(buyer_jhb, produce="tomatoes", quantity=1, unit="KG"))
    for lst in market.values():
        for fragment in coordinate_fragments(lst.farmer.location):
            assert fragment not in blob
        assert lst.farmer.email not in blob


def test_only_buyers_can_search_farmers(market):
    from rest_framework.exceptions import PermissionDenied

    with pytest.raises(PermissionDenied):
        services.search_recommended_farmers(market["near_full"].farmer, produce="x", quantity=1, unit="KG")


# --- Farmer → buyers ----------------------------------------------------------------

@pytest.fixture
def potato_farmer(db):
    f = farmer_at("Potato Farmer", gps=JHB)
    ProduceListingFactory(farmer=f, produce_name="Potatoes", quantity_available=500, price_per_unit=8)
    return f


def buyer_at(name, **loc):
    b = BuyerFactory(display_name=name)
    UserLocationFactory(user=b, **loc)
    return b


def test_farmer_sees_matching_buyers_with_partial_labels(potato_farmer):
    near = buyer_at("Near Buyer", town="Soweto", latitude=SOWETO[0], longitude=SOWETO[1])
    big = buyer_at("Big Buyer", municipality="City of Tshwane", town="Pretoria")
    BuyerRequirementFactory(buyer=near, produce_name="Potatoes", quantity_needed=200, max_price_per_unit=10)
    BuyerRequirementFactory(buyer=big, produce_name="Potatoes", quantity_needed=800)
    BuyerRequirementFactory(buyer=near, produce_name="Onions")  # farmer doesn't list onions
    BuyerRequirementFactory(buyer=near, produce_name="Potatoes", status="CLOSED")
    result = services.search_buyer_requirements(potato_farmer)
    assert [r["buyer_display_name"] for r in result["results"]] == ["Near Buyer", "Big Buyer"]
    big_match = result["results"][1]
    assert any("Partial supply: you have 500 kg of the 800 kg" in g for g in big_match["gaps"])
    near_match = result["results"][0]
    assert any("covering the 200 kg they need" in r for r in near_match["match_reasons"])
    assert RecommendationLog.objects.filter(direction="FARMER_TO_BUYER").count() == 1


def test_farmer_no_match_and_requirement_distance_limit(potato_farmer):
    assert services.search_buyer_requirements(potato_farmer)["count"] == 0
    far = buyer_at("Far Buyer", province=Province.WESTERN_CAPE, municipality="City of Cape Town", town="Cape Town")
    BuyerRequirementFactory(buyer=far, produce_name="Potatoes", max_distance_km=100)
    result = services.search_buyer_requirements(potato_farmer)
    assert result["count"] == 0 and "No open buyer requirements" in result["message"]


def test_dashboard_endpoints(potato_farmer, auth_client, buyer_jhb, market):
    BuyerRequirementFactory(buyer=buyer_jhb, produce_name="Potatoes", quantity_needed=100)
    res = auth_client(potato_farmer).get("/api/v1/farmers/me/recommended-buyers/")
    assert res.status_code == 200 and res.json()["count"] == 1
    BuyerRequirementFactory(buyer=buyer_jhb, produce_name="Tomatoes")
    res = auth_client(buyer_jhb).get("/api/v1/buyers/me/recommended-farmers/")
    assert res.status_code == 200
    assert {i["produce"] for i in res.json()["items"]} == {"Potatoes", "Tomatoes"}
    assert auth_client(buyer_jhb).get("/api/v1/farmers/me/recommended-buyers/").status_code == 403
    assert auth_client(potato_farmer).get("/api/v1/buyers/me/recommended-farmers/").status_code == 403


def test_adhoc_recommendation_endpoint(auth_client, buyer_jhb, market):
    res = auth_client(buyer_jhb).post("/api/v1/recommendations/farmers/", {
        "items": [{"produce": "Tomatoes", "quantity": "100", "unit": "KG"}], "max_distance_km": 60,
    }, format="json")
    assert res.status_code == 200, res.data
    assert {r["farmer_display_name"] for r in res.json()["items"][0]["results"]} == {"Near Full", "Partial Stock",
                                                                                     "Pretoria Premium"}
