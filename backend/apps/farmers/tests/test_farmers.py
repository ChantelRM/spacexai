from decimal import Decimal

import pytest

from apps.accounts.factories import BuyerFactory
from apps.ai.tests.helpers import coordinate_fragments
from apps.farmers.models import FarmerProfile
from apps.listings.models import ProduceListing
from apps.locations.factories import UserLocationFactory

pytestmark = pytest.mark.django_db

ME = "/api/v1/farmers/me/profile/"


def test_profile_lifecycle(farmer_client):
    assert farmer_client.get(ME).status_code == 404
    res = farmer_client.put(ME, {"farm_name": "Green Acres", "main_produce": ["Tomatoes", "tomatoes", " Spinach "],
                                 "farm_size_hectares": "4.50", "is_verified": True}, format="json")
    assert res.status_code == 201, res.data
    assert res.json()["main_produce"] == ["Tomatoes", "Spinach"]
    assert res.json()["is_verified"] is False  # admin-only
    assert farmer_client.patch(ME, {"bio": "Family farm"}, format="json").json()["bio"] == "Family farm"
    assert FarmerProfile.objects.count() == 1


def test_buyers_cannot_have_farmer_profile(buyer_client):
    assert buyer_client.put(ME, {"farm_name": "X"}, format="json").status_code == 403


def test_public_profile_hides_private_data(farmer, buyer_client, buyer):
    loc = UserLocationFactory(user=farmer, latitude=Decimal("-26.204100"), longitude=Decimal("28.047300"),
                              address_line="7 Secret Road")
    UserLocationFactory(user=buyer, town="Soweto", latitude=Decimal("-26.267800"), longitude=Decimal("27.858500"))
    FarmerProfile.objects.create(user=farmer, farm_name="Green Acres", is_verified=True)
    ProduceListing.objects.create(farmer=farmer, produce_name="Tomatoes", quantity_available=10, unit="KG",
                                  price_per_unit=5)
    res = buyer_client.get(f"/api/v1/farmers/{farmer.pk}/")
    assert res.status_code == 200
    body = res.json()
    assert body["farm_name"] == "Green Acres" and body["is_verified"] is True
    assert body["active_listings_count"] == 1
    assert body["location"]["distance"]["basis"] == "gps" and body["location"]["distance"]["km"] > 0
    text = res.content.decode()
    for fragment in coordinate_fragments(loc):
        assert fragment not in text
    assert farmer.email not in text and farmer.phone_number not in text and "Secret" not in text


def test_public_profile_404_for_buyers_and_unknown(farmer_client):
    assert farmer_client.get(f"/api/v1/farmers/{BuyerFactory().pk}/").status_code == 404
    assert farmer_client.get("/api/v1/farmers/999999/").status_code == 404
