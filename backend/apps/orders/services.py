"""
Order state machine. The ONLY place order status changes.

    PENDING ──farmer accepts──▶ ACCEPTED ──farmer──▶ DISPATCHED ──buyer confirms receipt──▶ DELIVERED ──▶ COMPLETED
       │                           │
       ├─farmer rejects──▶ REJECTED │
       └─buyer cancels──▶ CANCELLED ◀─either party, before DISPATCHED (with reason)

Stock is reserved (decremented) when the farmer accepts and restored if an
accepted order is cancelled. Payment is settled outside the platform.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.buyers.models import BuyerRequirement
from apps.core.notifications import notify
from apps.listings.models import ListingStatus, ProduceListing
from apps.listings.units import format_quantity

from .models import Order, OrderItem, OrderStatus, OrderStatusHistory, PaymentStatus

S = OrderStatus
CENT = Decimal("0.01")


class OrderConflict(ValidationError):
    """Raised for illegal transitions and insufficient stock (HTTP 400, code validation_error)."""


@dataclass(frozen=True)
class Transition:
    name: str
    sources: tuple
    target: str
    actor: str  # "farmer", "buyer" or "either"
    reason_required: bool = False


TRANSITIONS = {
    "accept": Transition("accept", (S.PENDING,), S.ACCEPTED, "farmer"),
    "reject": Transition("reject", (S.PENDING,), S.REJECTED, "farmer", reason_required=True),
    "dispatch": Transition("dispatch", (S.ACCEPTED,), S.DISPATCHED, "farmer"),
    "confirm_receipt": Transition("confirm_receipt", (S.DISPATCHED,), S.DELIVERED, "buyer"),
    "complete": Transition("complete", (S.DELIVERED,), S.COMPLETED, "either"),
    "cancel": Transition("cancel", (S.PENDING, S.ACCEPTED), S.CANCELLED, "either"),
}

MESSAGES = {
    "accept": "{farmer} accepted your order #{id}.",
    "reject": "{farmer} declined your order #{id}.",
    "dispatch": "Order #{id} from {farmer} is on its way.",
    "confirm_receipt": "{buyer} confirmed receipt of order #{id}.",
    "complete": "Order #{id} is complete.",
    "cancel": "Order #{id} was cancelled.",
}


def visible_orders(user):
    if user.role == Role.WHOLESALE_BUYER:
        return Order.objects.filter(buyer=user)
    return Order.objects.filter(farmer=user)


def get_order_for(user, order_id, *, for_update=False) -> Order:
    qs = visible_orders(user)
    if for_update:
        qs = qs.select_for_update()
    order = qs.filter(pk=order_id).first()
    if order is None:
        raise NotFound("Order not found.")
    return order


def _record(order, from_status, to_status, user, note=""):
    OrderStatusHistory.objects.create(order=order, from_status=from_status or "", to_status=to_status,
                                      changed_by=user, note=note[:500])


def order_summary(order: Order) -> dict:
    return {
        "order_id": order.pk,
        "status": order.status,
        "payment_status": order.payment_status,
        "farmer_id": order.farmer_id,
        "farmer_display_name": order.farmer.display_name,
        "buyer_id": order.buyer_id,
        "buyer_display_name": order.buyer.display_name,
        "total_amount": float(order.total_amount),
        "delivery_date": order.delivery_date.isoformat() if order.delivery_date else None,
        "items": [{"produce": i.produce_name, "quantity": float(i.quantity), "unit": i.unit,
                   "price_per_unit": float(i.price_per_unit), "line_total": float(i.line_total)}
                  for i in order.items.all()],
        "created_at": order.created_at.isoformat(),
    }


# --- Creating orders ---------------------------------------------------------------------

def validate_order_lines(buyer, items: list[dict]):
    """
    Check order lines without saving. Returns [(listing, quantity)].
    Rules: buyer only, active listings, one farmer, quantity > 0 and within current stock.
    """
    if getattr(buyer, "role", None) != Role.WHOLESALE_BUYER:
        raise PermissionDenied("Only wholesale buyers can place orders.")
    if not items:
        raise ValidationError({"items": ["Add at least one item."]})
    ids = [int(i["listing_id"]) for i in items]
    if len(ids) != len(set(ids)):
        raise ValidationError({"items": ["Each listing can only appear once in an order."]})
    listings = {lst.pk: lst for lst in ProduceListing.objects.active().filter(pk__in=ids).select_related("farmer")}
    lines = []
    for item in items:
        listing = listings.get(int(item["listing_id"]))
        if listing is None:
            raise ValidationError({"items": [f"Listing {item['listing_id']} is not available."]})
        quantity = Decimal(str(item["quantity"]))
        if quantity <= 0:
            raise ValidationError({"items": ["Quantities must be more than zero."]})
        if quantity > listing.quantity_available:
            raise ValidationError({"items": [
                f"Only {format_quantity(listing.quantity_available, listing.unit)} of {listing.produce_name} "
                f"is available."]})
        lines.append((listing, quantity))
    farmers = {listing.farmer_id for listing, _ in lines}
    if len(farmers) > 1:
        raise ValidationError({"items": ["An order can only contain items from one farmer."]})
    return lines


def lines_total(lines) -> Decimal:
    return sum(((listing.price_per_unit * qty).quantize(CENT) for listing, qty in lines), Decimal("0"))


@transaction.atomic
def create_order(buyer, *, items, delivery_date=None, delivery_notes="", buyer_requirement_id=None,
                 **_ignored) -> Order:
    lines = validate_order_lines(buyer, items)
    requirement = None
    if buyer_requirement_id:
        requirement = BuyerRequirement.objects.filter(pk=buyer_requirement_id, buyer=buyer).first()
        if requirement is None:
            raise ValidationError({"buyer_requirement_id": ["Requirement not found."]})
    farmer = lines[0][0].farmer
    order = Order.objects.create(buyer=buyer, farmer=farmer, delivery_date=delivery_date,
                                 delivery_notes=delivery_notes or "", buyer_requirement=requirement,
                                 total_amount=lines_total(lines))
    for listing, quantity in lines:
        OrderItem.objects.create(order=order, listing=listing, produce_name=listing.produce_name, unit=listing.unit,
                                 price_per_unit=listing.price_per_unit, quantity=quantity,
                                 line_total=(listing.price_per_unit * quantity).quantize(CENT))
    _record(order, "", S.PENDING, buyer, "Order placed")
    notify(farmer, "order_placed", f"New order #{order.pk} from {buyer.display_name}.", f"orders/{order.pk}")
    return order


# --- Transitions ---------------------------------------------------------------------------

def _reserve_stock(order):
    """Decrement stock for every line, atomically. Fails if any listing has too little."""
    for item in order.items.select_related("listing"):
        listing = ProduceListing.objects.select_for_update().get(pk=item.listing_id)
        if listing.status not in (ListingStatus.ACTIVE, ListingStatus.PAUSED):
            raise OrderConflict({"stock": [f"{item.produce_name} is no longer available."]})
        # Conditional UPDATE: safe even where select_for_update is a no-op (SQLite).
        updated = ProduceListing.objects.filter(pk=listing.pk, quantity_available__gte=item.quantity).update(
            quantity_available=F("quantity_available") - item.quantity)
        if not updated:
            raise OrderConflict({"stock": [
                f"Not enough {item.produce_name} in stock: "
                f"{format_quantity(listing.quantity_available, listing.unit)} left."]})
        listing.refresh_from_db()
        listing.save()  # syncs SOLD_OUT when it reaches 0


def _restore_stock(order):
    for item in order.items.all():
        ProduceListing.objects.filter(pk=item.listing_id).update(
            quantity_available=F("quantity_available") + item.quantity)
        listing = ProduceListing.objects.get(pk=item.listing_id)
        listing.save()  # SOLD_OUT -> ACTIVE if stock came back


def _check_actor(order, user, transition):
    is_buyer, is_farmer = user.pk == order.buyer_id, user.pk == order.farmer_id
    allowed = {"farmer": is_farmer, "buyer": is_buyer, "either": is_buyer or is_farmer}[transition.actor]
    if transition.name == "cancel" and order.status == S.PENDING and not is_buyer:
        allowed = False  # farmers reject pending orders instead of cancelling
    if not allowed:
        raise PermissionDenied(f"You can't {transition.name.replace('_', ' ')} this order.")


@transaction.atomic
def transition(user, order_id, action: str, *, reason: str = "") -> Order:
    if action not in TRANSITIONS:
        raise ValidationError({"action": [f"Unknown action {action!r}."]})
    t = TRANSITIONS[action]
    order = get_order_for(user, order_id, for_update=True)
    _check_actor(order, user, t)
    if order.status not in t.sources:
        raise OrderConflict({"status": [
            f"Can't {action.replace('_', ' ')} an order that is {order.get_status_display().lower()}."]})
    reason = (reason or "").strip()
    needs_reason = t.reason_required or (action == "cancel" and order.status == S.ACCEPTED)
    if needs_reason and not reason:
        raise ValidationError({"reason": ["Please give a reason."]})

    previous = order.status
    if action == "accept":
        _reserve_stock(order)
    elif action == "cancel" and previous == S.ACCEPTED:
        _restore_stock(order)

    order.status = t.target
    if action == "reject":
        order.rejection_reason = reason
    if action == "cancel":
        order.cancellation_reason = reason
        order.cancelled_by = user
    order.save()
    _record(order, previous, t.target, user, reason)

    other = order.buyer if user.pk == order.farmer_id else order.farmer
    message = MESSAGES[action].format(id=order.pk, farmer=order.farmer.display_name, buyer=order.buyer.display_name)
    notify(other, f"order_{t.target.lower()}", message, f"orders/{order.pk}")
    return order


@transaction.atomic
def set_payment_status(user, order_id, payment_status: str) -> Order:
    """Farmers mark PAID/UNPAID (they receive the money); either party may flag DISPUTED."""
    order = get_order_for(user, order_id, for_update=True)
    if payment_status not in PaymentStatus.values:
        raise ValidationError({"payment_status": ["Invalid payment status."]})
    if payment_status != PaymentStatus.DISPUTED and user.pk != order.farmer_id:
        raise PermissionDenied("Only the farmer can mark an order as paid or unpaid.")
    if order.status in (S.PENDING, S.REJECTED, S.CANCELLED) and payment_status == PaymentStatus.PAID:
        raise ValidationError({"payment_status": ["Only accepted orders can be marked as paid."]})
    order.payment_status = payment_status
    order.save(update_fields=["payment_status", "updated_at"])
    _record(order, order.status, order.status, user, f"Payment status: {payment_status}")
    other = order.buyer if user.pk == order.farmer_id else order.farmer
    notify(other, "order_payment", f"Order #{order.pk} payment marked {payment_status.lower()}.", f"orders/{order.pk}")
    return order
