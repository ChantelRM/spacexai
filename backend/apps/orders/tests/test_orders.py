from decimal import Decimal

import pytest
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.factories import BuyerFactory, FarmerFactory
from apps.ai.models import PendingAction
from apps.ai.tests.helpers import FakeGrok, text_turn, tool_turn
from apps.core.models import Notification
from apps.listings.factories import ProduceListingFactory
from apps.listings.models import ProduceListing
from apps.orders import services
from apps.orders.models import Order, OrderStatusHistory

pytestmark = pytest.mark.django_db
ORDERS = "/api/v1/orders/"


@pytest.fixture
def listing(farmer):
    return ProduceListingFactory(farmer=farmer, quantity_available=Decimal("100"), price_per_unit=Decimal("12.50"))


def place(buyer, listing, qty="40"):
    return services.create_order(buyer, items=[{"listing_id": listing.pk, "quantity": qty}])


def act(user, order, action, reason=""):
    return services.transition(user, order.pk, action, reason=reason)


def stock(listing):
    listing.refresh_from_db()
    return listing.quantity_available, listing.status


# --- Creating ---------------------------------------------------------------------

def test_create_order_snapshots_prices_and_notifies(buyer, listing, farmer):
    order = place(buyer, listing, "40")
    assert order.status == "PENDING" and order.farmer == farmer
    assert order.total_amount == Decimal("500.00")
    item = order.items.get()
    assert (item.produce_name, item.price_per_unit, item.line_total) == ("Tomatoes", Decimal("12.50"), Decimal("500.00"))
    assert stock(listing) == (Decimal("100"), "ACTIVE")  # nothing reserved until accepted
    assert Notification.objects.filter(user=farmer, type="order_placed").exists()
    assert OrderStatusHistory.objects.get(order=order).to_status == "PENDING"


def test_order_must_be_single_farmer_and_in_stock(buyer, listing):
    other = ProduceListingFactory(farmer=FarmerFactory())
    with pytest.raises(ValidationError, match="one farmer"):
        services.create_order(buyer, items=[{"listing_id": listing.pk, "quantity": 1},
                                            {"listing_id": other.pk, "quantity": 1}])
    with pytest.raises(ValidationError, match="Only 100 kg"):
        place(buyer, listing, "101")
    listing.status = "PAUSED"
    listing.save()
    with pytest.raises(ValidationError, match="not available"):
        place(buyer, listing, "1")


def test_farmers_cannot_place_orders(farmer, listing, farmer_client):
    with pytest.raises(PermissionDenied):
        place(farmer, listing)
    res = farmer_client.post(ORDERS, {"items": [{"listing_id": listing.pk, "quantity": "1"}]}, format="json")
    assert res.status_code == 403


# --- State machine -----------------------------------------------------------------

def test_happy_path_with_stock_and_history(buyer, farmer, listing):
    order = place(buyer, listing, "100")
    act(farmer, order, "accept")
    assert stock(listing) == (Decimal("0"), "SOLD_OUT")
    act(farmer, order, "dispatch")
    act(buyer, order, "confirm_receipt")
    order = act(buyer, order, "complete")
    assert order.status == "COMPLETED"
    assert list(order.history.values_list("to_status", flat=True)) == [
        "PENDING", "ACCEPTED", "DISPATCHED", "DELIVERED", "COMPLETED"]
    assert Notification.objects.filter(user=buyer, type="order_accepted").exists()


@pytest.mark.parametrize("actor,action,setup", [
    ("buyer", "accept", []),
    ("farmer", "confirm_receipt", ["accept", "dispatch"]),
    ("buyer", "dispatch", ["accept"]),
    ("farmer", "cancel", []),  # farmers reject pending orders instead
])
def test_wrong_party_is_denied(buyer, farmer, listing, actor, action, setup):
    order = place(buyer, listing)
    for step in setup:
        act(farmer, order, step)
    with pytest.raises(PermissionDenied):
        act({"buyer": buyer, "farmer": farmer}[actor], order, action)


@pytest.mark.parametrize("setup,action", [
    ([], "dispatch"), ([], "complete"), (["accept"], "accept"), (["accept", "dispatch"], "cancel"),
    (["reject"], "accept"), (["accept", "dispatch"], "reject"),
])
def test_illegal_transitions(buyer, farmer, listing, setup, action):
    order = place(buyer, listing)
    for step in setup:
        act(farmer, order, step, reason="no stock")
    actor = buyer if action == "cancel" else farmer
    with pytest.raises(ValidationError):
        act(actor, order, action, reason="because")


def test_reject_requires_reason(buyer, farmer, listing):
    order = place(buyer, listing)
    with pytest.raises(ValidationError, match="reason"):
        act(farmer, order, "reject")
    assert act(farmer, order, "reject", reason="Out of season").rejection_reason == "Out of season"


def test_cancel_after_accept_restores_stock_and_needs_reason(buyer, farmer, listing):
    order = place(buyer, listing, "100")
    act(farmer, order, "accept")
    with pytest.raises(ValidationError):
        act(buyer, order, "cancel")
    order = act(farmer, order, "cancel", reason="Truck broke down")
    assert order.cancelled_by == farmer
    assert stock(listing) == (Decimal("100"), "ACTIVE")


def test_buyer_cancels_pending_without_reason(buyer, listing):
    assert act(buyer, place(buyer, listing), "cancel").status == "CANCELLED"


def test_accept_fails_when_stock_ran_out(buyer, farmer, listing):
    """Two orders racing for the last stock: the second accept must fail and change nothing."""
    first = place(buyer, listing, "70")
    second = place(BuyerFactory(), listing, "70")
    act(farmer, first, "accept")
    with pytest.raises(ValidationError, match="Not enough"):
        act(farmer, second, "accept")
    assert Order.objects.get(pk=second.pk).status == "PENDING"
    assert stock(listing) == (Decimal("30"), "ACTIVE")


def test_conditional_update_guards_stock_even_without_row_locks(buyer, farmer, listing):
    order = place(buyer, listing, "60")
    # Simulate another transaction taking stock between our read and our write.
    ProduceListing.objects.filter(pk=listing.pk).update(quantity_available=Decimal("10"))
    with pytest.raises(ValidationError):
        act(farmer, order, "accept")
    assert stock(listing)[0] == Decimal("10")


def test_payment_status(buyer, farmer, listing):
    order = place(buyer, listing)
    with pytest.raises(ValidationError):
        services.set_payment_status(farmer, order.pk, "PAID")  # not accepted yet
    act(farmer, order, "accept")
    with pytest.raises(PermissionDenied):
        services.set_payment_status(buyer, order.pk, "PAID")
    assert services.set_payment_status(farmer, order.pk, "PAID").payment_status == "PAID"
    assert services.set_payment_status(buyer, order.pk, "DISPUTED").payment_status == "DISPUTED"


# --- API -------------------------------------------------------------------------------

def test_api_flow_and_visibility(buyer_client, farmer_client, auth_client, listing):
    res = buyer_client.post(ORDERS, {"items": [{"listing_id": listing.pk, "quantity": "10"}],
                                     "delivery_date": "2026-11-20"}, format="json")
    assert res.status_code == 201, res.data
    oid = res.json()["id"]
    assert res.json()["farmer"]["display_name"] == listing.farmer.display_name
    assert "email" not in str(res.json())
    assert farmer_client.post(f"{ORDERS}{oid}/accept/").json()["status"] == "ACCEPTED"
    assert farmer_client.post(f"{ORDERS}{oid}/dispatch/").json()["status"] == "DISPATCHED"
    assert buyer_client.post(f"{ORDERS}{oid}/confirm-receipt/").json()["status"] == "DELIVERED"
    assert buyer_client.post(f"{ORDERS}{oid}/complete/").json()["status"] == "COMPLETED"
    res = farmer_client.post(f"{ORDERS}{oid}/accept/")
    assert res.status_code == 400 and res.json()["error"]["code"] == "validation_error"

    outsider = auth_client(BuyerFactory())
    assert outsider.get(f"{ORDERS}{oid}/").status_code == 404
    assert outsider.get(ORDERS).json()["count"] == 0
    other_farmer = auth_client(FarmerFactory())
    assert other_farmer.post(f"{ORDERS}{oid}/accept/").status_code == 404
    assert buyer_client.get(f"{ORDERS}?status=COMPLETED").json()["count"] == 1
    assert len(buyer_client.get(f"{ORDERS}{oid}/").json()["history"]) == 5


def test_notifications_api(buyer, buyer_client, listing, farmer_client):
    place(buyer, listing)
    res = farmer_client.get("/api/v1/notifications/?unread=true")
    assert res.json()["count"] == 1
    nid = res.json()["results"][0]["id"]
    assert farmer_client.get("/api/v1/notifications/unread-count/").json() == {"unread": 1}
    assert buyer_client.post(f"/api/v1/notifications/{nid}/read/").status_code == 404  # not theirs
    assert farmer_client.post(f"/api/v1/notifications/{nid}/read/").json()["is_read"] is True
    assert farmer_client.post("/api/v1/notifications/read-all/").json() == {"unread": 0}


# --- AI tools --------------------------------------------------------------------------

def chat(client, monkeypatch, *turns):
    monkeypatch.setattr("apps.ai.client.create_response", FakeGrok(*turns))
    res = client.post("/api/v1/ai/chat/", {"message": "go"}, format="json")
    assert res.status_code == 200, res.data
    return res.json()


def test_ai_order_stays_pending_until_confirmed(buyer_client, buyer, listing, monkeypatch):
    body = chat(buyer_client, monkeypatch,
                tool_turn("create_order", items=[{"listing_id": listing.pk, "quantity": 20}],
                          delivery_date="2026-11-20"),
                text_turn("Please confirm the order."))
    pending = body["pending_action"]
    assert pending["tool_name"] == "create_order"
    assert pending["summary"] == (
        f"Place an order with {listing.farmer.display_name}: 20 kg Tomatoes at R12.50/kg = R250.00. "
        "Total R250.00, delivery by 20 Nov 2026. The farmer must accept it; payment is arranged outside the app.")
    assert Order.objects.count() == 0
    res = buyer_client.post(f"/api/v1/ai/actions/{pending['id']}/confirm/")
    assert res.status_code == 200, res.data
    order = Order.objects.get()
    assert order.status == "PENDING" and order.buyer == buyer and order.total_amount == Decimal("250.00")
    assert buyer_client.post(f"/api/v1/ai/actions/{pending['id']}/confirm/").status_code == 409
    assert Order.objects.count() == 1


def test_ai_order_invalid_lines_never_become_pending(buyer_client, listing, monkeypatch):
    body = chat(buyer_client, monkeypatch,
                tool_turn("create_order", items=[{"listing_id": listing.pk, "quantity": 5000}]),
                text_turn("Not enough stock."))
    assert body["tool_calls"] == [{"name": "create_order", "status": "invalid"}]
    assert PendingAction.objects.count() == 0


def test_ai_respond_to_order_requires_confirmation(farmer_client, farmer, buyer, listing, monkeypatch):
    order = place(buyer, listing, "30")
    body = chat(farmer_client, monkeypatch, tool_turn("respond_to_order", order_id=order.pk, decision="accept"),
                text_turn("Confirm to accept."))
    assert body["pending_action"]["summary"].startswith(f"Accept order #{order.pk} from {buyer.display_name}")
    assert Order.objects.get(pk=order.pk).status == "PENDING"
    farmer_client.post(f"/api/v1/ai/actions/{body['pending_action']['id']}/confirm/")
    assert Order.objects.get(pk=order.pk).status == "ACCEPTED"
    assert stock(listing)[0] == Decimal("70")


def test_ai_respond_rejects_other_farmers_orders(auth_client, buyer, listing, monkeypatch):
    order = place(buyer, listing)
    body = chat(auth_client(FarmerFactory()), monkeypatch,
                tool_turn("respond_to_order", order_id=order.pk, decision="accept"), text_turn("No."))
    assert body["tool_calls"][0]["status"] == "invalid"


def test_ai_get_my_orders_and_compare(buyer_client, buyer, listing, monkeypatch):
    place(buyer, listing)
    other = ProduceListingFactory(price_per_unit=Decimal("9"))
    body = chat(buyer_client, monkeypatch, tool_turn("get_my_orders"),
                tool_turn("compare_listings", listing_ids=[listing.pk, other.pk]), text_turn("Done"))
    assert body["data"]["get_my_orders"]["count"] == 1
    compare = body["data"]["compare_listings"]
    assert compare["count"] == 2 and compare["cheapest_listing_id"] == other.pk
