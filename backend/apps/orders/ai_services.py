"""Order services for the AI tools. Every write here runs only after the user confirmed a PendingAction."""
from rest_framework.exceptions import ValidationError

from . import services


def create_order(user, *, items, delivery_date=None, delivery_notes="", buyer_requirement_id=None, **_ignored):
    order = services.create_order(user, items=items, delivery_date=delivery_date, delivery_notes=delivery_notes,
                                  buyer_requirement_id=buyer_requirement_id)
    return {"available": True, **services.order_summary(order),
            "note": "The order is PENDING until the farmer accepts it. Payment is arranged outside the app."}


def get_my_orders(user, *, status=None, limit=10, **_ignored):
    qs = services.visible_orders(user).select_related("buyer", "farmer").prefetch_related("items")
    if status:
        qs = qs.filter(status=status)
    orders = list(qs.order_by("-created_at")[:limit])
    result = {"available": True, "count": len(orders), "results": [services.order_summary(o) for o in orders]}
    if not orders:
        result["message"] = "You have no orders" + (f" with status {status}." if status else " yet.")
    return result


def respond_to_order(user, *, order_id, decision, reason="", **_ignored):
    if decision not in ("accept", "reject"):
        raise ValidationError({"decision": ["Use accept or reject."]})
    order = services.transition(user, order_id, decision, reason=reason)
    return {"available": True, **services.order_summary(order)}

