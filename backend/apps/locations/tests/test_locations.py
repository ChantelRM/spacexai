from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.accounts.factories import FarmerFactory
from apps.locations.distance import (
    approximate_distance,
    haversine_km,
    proximity_rank,
    proximity_tier,
    within_km,
)
from apps.locations.factories import UserLocationFactory
from apps.locations.models import Province, UserLocation
from apps.locations.serializers import public_location

ME = reverse("locations:me")

JHB = (-26.2041, 28.0473)
PTA = (-25.7479, 28.2293)
CPT = (-33.9249, 18.4241)
DBN = (-29.8587, 31.0218)


def loc(province="GAUTENG", municipality="City of Johannesburg", town="Johannesburg", lat=None, lng=None):
    return SimpleNamespace(province=province, municipality=municipality, town=town, latitude=lat, longitude=lng)


# --- Haversine ---------------------------------------------------------------

def test_haversine_known_pairs():
    assert 53 <= haversine_km(*JHB, *PTA) <= 57
    assert 1250 <= haversine_km(*JHB, *CPT) <= 1275
    assert 495 <= haversine_km(*JHB, *DBN) <= 510
    assert haversine_km(*JHB, *JHB) == 0
    # Symmetric and accepts Decimals
    assert haversine_km(*PTA, *JHB) == pytest.approx(haversine_km(*JHB, *PTA))
    assert haversine_km(Decimal("-26.2041"), Decimal("28.0473"), *PTA) == pytest.approx(haversine_km(*JHB, *PTA))


def test_approximate_distance_gps_is_rounded():
    result = approximate_distance(loc(lat=JHB[0], lng=JHB[1]), loc(lat=PTA[0], lng=PTA[1]))
    assert result["basis"] == "gps"
    assert isinstance(result["km"], int) and 53 <= result["km"] <= 57
    assert result["label"] == f"≈ {result['km']} km"


def test_approximate_distance_never_reports_zero():
    assert approximate_distance(loc(lat=JHB[0], lng=JHB[1]), loc(lat=JHB[0], lng=JHB[1]))["km"] == 1


@pytest.mark.parametrize(
    "other,expected",
    [
        (loc(), "same_town"),
        (loc(town="  johannesburg "), "same_town"),  # case/whitespace-insensitive
        (loc(town="Soweto"), "same_municipality"),
        (loc(municipality="City of Tshwane", town="Pretoria"), "same_province"),
        (loc(province="WESTERN_CAPE", municipality="City of Cape Town", town="Cape Town"), "different_province"),
        (None, "unknown"),
    ],
)
def test_fallback_tiers(other, expected):
    me = loc(lat=JHB[0], lng=JHB[1])  # GPS on one side only -> still falls back
    result = approximate_distance(me, other)
    assert result == {"km": None, "basis": expected, "label": result["label"]}
    assert proximity_tier(me, other) == expected


def test_proximity_rank_orders_with_and_without_gps():
    me = loc(lat=JHB[0], lng=JHB[1])
    candidates = {
        "pta_gps": loc(municipality="City of Tshwane", town="Pretoria", lat=PTA[0], lng=PTA[1]),
        "same_town": loc(),
        "soweto": loc(town="Soweto"),
        "other_muni": loc(municipality="Ekurhuleni", town="Benoni"),
        "cpt_gps": loc(province="WESTERN_CAPE", municipality="City of Cape Town", town="Cape Town", lat=CPT[0], lng=CPT[1]),
        "kzn": loc(province="KWAZULU_NATAL", municipality="eThekwini", town="Durban"),
        "nowhere": None,
    }
    ordered = sorted(candidates, key=lambda k: proximity_rank(me, candidates[k]))
    assert ordered == ["same_town", "soweto", "pta_gps", "other_muni", "kzn", "cpt_gps", "nowhere"]


def test_within_km():
    me = loc(lat=JHB[0], lng=JHB[1])
    assert within_km(me, loc(municipality="City of Tshwane", town="Pretoria", lat=PTA[0], lng=PTA[1]), 60)
    assert not within_km(me, loc(municipality="City of Tshwane", town="Pretoria", lat=PTA[0], lng=PTA[1]), 50)
    assert within_km(me, loc(town="Soweto"), 50)
    assert not within_km(me, loc(province="LIMPOPO", municipality="Polokwane", town="Polokwane"), 100)
    assert within_km(me, None, None)


# --- Model validation ----------------------------------------------------------

@pytest.mark.django_db
def test_db_constraint_lat_lng_both_or_neither():
    with pytest.raises(IntegrityError), transaction.atomic():
        UserLocationFactory(latitude=Decimal("-26.2"), longitude=None)


# --- API ---------------------------------------------------------------------

VALID = {
    "province": Province.LIMPOPO,
    "municipality": "Polokwane Local Municipality",
    "town": "Polokwane",
    "latitude": -23.904449123,  # more precision than stored; rounded to 6 dp
    "longitude": 29.468839,
    "preferred_delivery_areas": [{"province": "GAUTENG", "municipality": "City of Tshwane", "town": "Pretoria"}],
}


@pytest.mark.django_db
def test_get_before_set_is_404(farmer_client):
    res = farmer_client.get(ME)
    assert res.status_code == 404
    assert res.data["error"]["code"] == "not_found"


@pytest.mark.django_db
def test_put_creates_then_replaces_and_owner_sees_coordinates(farmer_client, farmer):
    res = farmer_client.put(ME, VALID, format="json")
    assert res.status_code == 201, res.data
    assert res.json()["latitude"] == pytest.approx(-23.904449)  # JSON number, 6 dp
    assert res.data["province_display"] == "Limpopo"
    res = farmer_client.put(ME, {**VALID, "town": "Seshego", "latitude": None, "longitude": None}, format="json")
    assert res.status_code == 200
    assert res.data["latitude"] is None
    assert UserLocation.objects.filter(user=farmer).count() == 1


@pytest.mark.django_db
def test_patch(farmer_client):
    assert farmer_client.patch(ME, {"town": "X"}, format="json").status_code == 404
    farmer_client.put(ME, VALID, format="json")
    res = farmer_client.patch(ME, {"town": "  Seshego  "}, format="json")
    assert res.status_code == 200
    assert res.data["town"] == "Seshego"
    assert res.data["latitude"] is not None


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {**VALID, "longitude": None},
        {**VALID, "latitude": None},
        {k: v for k, v in VALID.items() if k != "longitude"},
    ],
)
def test_lat_lng_both_or_neither_via_api(farmer_client, payload):
    res = farmer_client.put(ME, payload, format="json")
    assert res.status_code == 400
    assert res.data["error"]["code"] == "validation_error"
    assert "latitude" in res.data["error"]["details"]


@pytest.mark.django_db
def test_patch_one_coordinate_on_existing_gps_location_is_fine_but_null_one_is_not(farmer_client):
    farmer_client.put(ME, VALID, format="json")
    assert farmer_client.patch(ME, {"latitude": -23.9}, format="json").status_code == 200
    assert farmer_client.patch(ME, {"latitude": None}, format="json").status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload",
    [
        {**VALID, "province": "ATLANTIS"},
        {**VALID, "latitude": 95, "longitude": 10},
        {**VALID, "preferred_delivery_areas": [{"province": "NOPE"}]},
        {**VALID, "preferred_delivery_areas": "Pretoria"},
    ],
)
def test_invalid_location_payloads(farmer_client, payload):
    assert farmer_client.put(ME, payload, format="json").status_code == 400


@pytest.mark.django_db
def test_location_requires_auth(api_client):
    assert api_client.get(ME).status_code == 401


@pytest.mark.django_db
def test_users_only_see_their_own_location(farmer_client, buyer_client):
    farmer_client.put(ME, VALID, format="json")
    res = buyer_client.get(ME)
    assert res.status_code == 404  # the buyer never sees the farmer's record


@pytest.mark.django_db
def test_public_location_hides_coordinates_and_address():
    owner_loc = UserLocationFactory(latitude=Decimal("-25.747900"), longitude=Decimal("28.229300"),
                                    address_line="12 Secret Farm Road", municipality="City of Tshwane", town="Pretoria")
    viewer_loc = UserLocationFactory(user=FarmerFactory(), latitude=Decimal("-26.204100"), longitude=Decimal("28.047300"))
    data = public_location(owner_loc, viewer_loc)
    assert set(data) == {"province", "province_display", "municipality", "town", "distance"}
    blob = str(data)
    assert "25.7479" not in blob and "28.2293" not in blob and "Secret" not in blob
    assert data["distance"]["basis"] == "gps"
