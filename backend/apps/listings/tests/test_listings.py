import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.accounts.factories import FarmerFactory
from apps.ai.models import PendingAction
from apps.ai.tests.helpers import text_turn, tool_turn
from apps.listings import services
from apps.listings.models import ListingStatus, ProduceListing
from apps.listings.units import convert_quantity, produce_key, produce_matches, units_compatible

pytestmark = pytest.mark.django_db

MINE = "/api/v1/listings/mine/"
VALID = {"produce_name": "Tomatoes", "category": "vegetables", "quantity_available": "120.00", "unit": "KG",
         "price_per_unit": "12.50", "quality_grade": "GRADE_A"}


def mine(pk, suffix=""):
    return f"{MINE}{pk}/{suffix}"


@pytest.fixture(autouse=True)
def media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def image_file(fmt="PNG", size=(20, 20), name="photo.png"):
    buf = io.BytesIO()
    Image.new("RGB", size, "green").save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


# --- Units and produce keys ---------------------------------------------------

def test_unit_conversion():
    assert convert_quantity(Decimal("2"), "TONNE", "KG") == Decimal("2000")
    assert convert_quantity(Decimal("500"), "KG", "TONNE") == Decimal("0.5")
    assert convert_quantity(5, "BAG", "BAG") == 5
    assert convert_quantity(5, "BAG", "KG") is None
    assert units_compatible("KG", "TONNE") and not units_compatible("CRATE", "KG")


@pytest.mark.parametrize("name,key", [("Tomatoes", "tomato"), ("  Cherry   TOMATOES ", "cherry tomato"),
                                      ("Potatoes", "potato"), ("Strawberries", "strawberry"),
                                      ("Spinach", "spinach"), ("Onions", "onion"), ("Grass", "grass")])
def test_produce_key(name, key):
    assert produce_key(name) == key


def test_produce_matches():
    assert produce_matches("tomato", "cherry tomato")
    assert not produce_matches("tomato", "potato")
    assert not produce_matches("", "potato")


# --- API ------------------------------------------------------------------------

def test_farmer_crud(farmer_client):
    res = farmer_client.post(MINE, VALID, format="json")
    assert res.status_code == 201, res.data
    body = res.json()
    assert body["produce_key"] == "tomato" and body["status"] == "ACTIVE" and body["category_name"] == "Vegetables"
    pk = body["id"]
    assert farmer_client.patch(mine(pk), {"price_per_unit": "11.00"}, format="json").json()["price_per_unit"] == "11.00"
    assert farmer_client.get(MINE).json()["count"] == 1
    assert farmer_client.delete(mine(pk)).status_code == 204
    assert ProduceListing.objects.get(pk=pk).status == ListingStatus.DELETED  # soft delete
    assert farmer_client.get(MINE).json()["count"] == 0
    assert farmer_client.get(mine(pk)).status_code == 404


def test_buyers_cannot_create_listings(buyer_client):
    res = buyer_client.post(MINE, VALID, format="json")
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "permission_denied"


def test_only_owner_can_edit(farmer_client, auth_client):
    pk = farmer_client.post(MINE, VALID, format="json").json()["id"]
    other = auth_client(FarmerFactory())
    assert other.patch(mine(pk), {"price_per_unit": "1"}, format="json").status_code == 404
    assert other.delete(mine(pk)).status_code == 404
    assert other.post(mine(pk, "pause/")).status_code == 404


def test_validation(farmer_client):
    bad = {**VALID, "quantity_available": "-1", "unit": "SACK", "available_from": "2026-12-10",
           "available_until": "2026-12-01"}
    res = farmer_client.post(MINE, bad, format="json")
    assert res.status_code == 400
    assert {"quantity_available", "unit"} <= set(res.json()["error"]["details"])
    res = farmer_client.post(MINE, {**VALID, "available_from": "2026-12-10", "available_until": "2026-12-01"},
                             format="json")
    assert "available_until" in res.json()["error"]["details"]


def test_pause_resume_and_sold_out(farmer_client):
    pk = farmer_client.post(MINE, VALID, format="json").json()["id"]
    assert farmer_client.post(mine(pk, "pause/")).json()["status"] == "PAUSED"
    assert not ProduceListing.objects.active().filter(pk=pk).exists()
    assert farmer_client.post(mine(pk, "pause/")).status_code == 400
    assert farmer_client.post(mine(pk, "resume/")).json()["status"] == "ACTIVE"
    assert farmer_client.patch(mine(pk), {"quantity_available": "0"}, format="json").json()["status"] == "SOLD_OUT"
    assert farmer_client.patch(mine(pk), {"quantity_available": "5"}, format="json").json()["status"] == "ACTIVE"
    assert farmer_client.get(MINE + "?status=ACTIVE").json()["count"] == 1


def test_expired_listing_not_active(farmer):
    listing = ProduceListing.objects.create(farmer=farmer, produce_name="Beans", quantity_available=5, unit="KG",
                                            price_per_unit=10, available_from=date.today() - timedelta(days=10),
                                            available_until=date.today() - timedelta(days=1))
    assert not ProduceListing.objects.active().filter(pk=listing.pk).exists()


def test_images(farmer_client):
    pk = farmer_client.post(MINE, VALID, format="json").json()["id"]
    res = farmer_client.post(mine(pk, "images/"), {"image": image_file()}, format="multipart")
    assert res.status_code == 201, res.data
    image_id = res.json()["id"]
    assert len(farmer_client.get(mine(pk)).json()["images"]) == 1

    not_image = SimpleUploadedFile("x.png", b"not an image", content_type="image/png")
    assert farmer_client.post(mine(pk, "images/"), {"image": not_image}, format="multipart").status_code == 400
    gif = image_file("GIF", name="a.gif")
    assert farmer_client.post(mine(pk, "images/"), {"image": gif}, format="multipart").status_code == 400

    for _ in range(4):
        assert farmer_client.post(mine(pk, "images/"), {"image": image_file()}, format="multipart").status_code == 201
    res = farmer_client.post(mine(pk, "images/"), {"image": image_file()}, format="multipart")
    assert res.status_code == 400  # max 5

    assert farmer_client.delete(mine(pk, f"images/{image_id}/")).status_code == 204
    assert farmer_client.delete(mine(pk, f"images/{image_id}/")).status_code == 404


def test_image_too_large(farmer_client, monkeypatch):
    import apps.listings.serializers as s

    monkeypatch.setattr(s, "MAX_IMAGE_BYTES", 100)
    pk = farmer_client.post(MINE, VALID, format="json").json()["id"]
    res = farmer_client.post(mine(pk, "images/"), {"image": image_file(size=(200, 200))}, format="multipart")
    assert res.status_code == 400
    assert "5 MB" in res.json()["error"]["message"]


def test_categories(farmer_client):
    res = farmer_client.get("/api/v1/listings/categories/")
    assert [c["slug"] for c in res.json()][:2] == ["dairy", "fruits"]
    assert len(res.json()) == 8


# --- Service + AI tool ----------------------------------------------------------

def test_service_create_and_update(farmer):
    created = services.create_or_update_listing(farmer, produce="Potatoes", quantity=Decimal("500"), unit="KG",
                                                price_per_unit=Decimal("8"), category="vegetables")
    assert created["created"] and created["quantity"] == 500.0
    updated = services.create_or_update_listing(farmer, listing_id=created["listing_id"], produce="Potatoes",
                                                quantity=Decimal("450"), unit="KG", price_per_unit=Decimal("7.5"))
    assert not updated["created"] and updated["price_per_unit"] == 7.5
    assert ProduceListing.objects.count() == 1


def test_service_rejects_other_farmers_listing_and_buyers(farmer, buyer):
    from rest_framework.exceptions import NotFound, PermissionDenied

    other = services.create_or_update_listing(FarmerFactory(), produce="Beans", quantity=1, unit="KG",
                                              price_per_unit=1)
    with pytest.raises(NotFound):
        services.create_or_update_listing(farmer, listing_id=other["listing_id"], produce="Beans", quantity=1,
                                          unit="KG", price_per_unit=1)
    with pytest.raises(PermissionDenied):
        services.create_or_update_listing(buyer, produce="Beans", quantity=1, unit="KG", price_per_unit=1)


def test_ai_listing_is_only_created_after_confirmation(farmer_client, farmer, fake_grok_listing):
    body = fake_grok_listing(farmer_client, produce="Potatoes", quantity=500, unit="KG", price_per_unit=8,
                             quality_grade="PREMIUM")
    assert ProduceListing.objects.count() == 0
    assert body["pending_action"]["summary"].startswith("Create a listing: 500 kg Potatoes at R8.00/kg, Premium")
    res = farmer_client.post(f"/api/v1/ai/actions/{body['pending_action']['id']}/confirm/")
    assert res.status_code == 200, res.data
    listing = ProduceListing.objects.get()
    assert listing.farmer == farmer and listing.quantity_available == 500 and listing.quality_grade == "PREMIUM"
    assert res.json()["result"]["listing_id"] == listing.pk


def test_ai_cannot_update_someone_elses_listing(farmer_client, fake_grok_listing):
    other = services.create_or_update_listing(FarmerFactory(), produce="Beans", quantity=1, unit="KG",
                                              price_per_unit=1)
    body = fake_grok_listing(farmer_client, listing_id=other["listing_id"], produce="Beans", quantity=99,
                             unit="KG", price_per_unit=1)
    res = farmer_client.post(f"/api/v1/ai/actions/{body['pending_action']['id']}/confirm/")
    assert res.status_code == 404
    assert ProduceListing.objects.get(pk=other["listing_id"]).quantity_available == 1
    assert PendingAction.objects.get().status == "failed"


@pytest.fixture
def fake_grok_listing(monkeypatch):
    from apps.ai.tests.helpers import FakeGrok

    def _run(client, **args):
        monkeypatch.setattr("apps.ai.client.create_response",
                            FakeGrok(tool_turn("create_or_update_listing", **args), text_turn("Please confirm.")))
        res = client.post("/api/v1/ai/chat/", {"message": "list it"}, format="json")
        assert res.status_code == 200, res.data
        return res.json()

    return _run
