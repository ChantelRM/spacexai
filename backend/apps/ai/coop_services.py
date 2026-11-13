"""
AI-facing wrappers for the cooperative commitment tools. Each one only runs
after the user confirmed a PendingAction, and delegates to the owning app's
services so the API and the AI share one set of rules.
"""
from __future__ import annotations

from datetime import datetime, time

from django.utils import timezone

from apps.bulk import services as bulk
from apps.equipment import services as equipment
from apps.transport import services as transport


def join_bulk_purchase(user, *, bulk_purchase_id, quantity, **_ignored) -> dict:
    member = bulk.join(user, bulk_purchase_id, quantity)
    return {"available": True, "bulk_purchase_id": bulk_purchase_id, "quantity": float(member.quantity),
            "calculated_contribution": float(member.calculated_contribution), "confirmed": member.confirmed,
            "note": "You joined. Your contribution is not committed until you confirm it separately."}


def confirm_bulk_purchase_contribution(user, *, bulk_purchase_id, **_ignored) -> dict:
    member = bulk.confirm(user, bulk_purchase_id)
    return {"available": True, "bulk_purchase_id": bulk_purchase_id, "confirmed": True,
            "calculated_contribution": float(member.calculated_contribution),
            "note": "Payment is made to the organiser outside the app."}


def join_transport_request(user, *, transport_request_id, **load) -> dict:
    p = transport.join(user, transport_request_id, **load)
    return {"available": True, "transport_request_id": transport_request_id,
            "calculated_share": float(p.calculated_share) if p.calculated_share is not None else None,
            "note": "You joined the trip. Confirm your share once the cost is quoted."}


def _aware(d, end=False):
    return timezone.make_aware(datetime.combine(d, time(17, 0) if end else time(7, 0)),
                               timezone.get_current_timezone())


def request_equipment_booking(user, *, equipment_id, start_date, end_date, quantity=None, notes="", **_ignored):
    booking = equipment.request_booking(user, equipment_id=equipment_id, start=_aware(start_date),
                                        end=_aware(end_date, end=True), quantity=quantity, notes=notes)
    return {"available": True, "booking_id": booking.pk, "status": booking.status,
            "estimated_cost": float(booking.estimated_cost),
            "note": "Booking requested. The owner must approve it."}
