"""
Equipment and storage sharing.

- Equipment: no two APPROVED bookings may overlap (checked when requesting
  and again, under lock, when the owner approves).
- Storage (cold storage, warehouses): concurrent APPROVED bookings are fine
  while their total tonnes stay within capacity.
"""
from __future__ import annotations

import math
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.core.costs import to_cents
from apps.core.notifications import notify
from apps.locations.distance import approximate_distance, proximity_rank, within_km
from apps.locations.models import UserLocation

from .models import BookingStatus, EquipmentBooking, EquipmentListing, RateUnit

B = BookingStatus


def _require_farmer(user):
    if getattr(user, "role", None) != Role.FARMER:
        raise PermissionDenied("Equipment sharing is for farmers.")


def estimate_cost(listing, start, end, quantity=None) -> Decimal:
    seconds = (end - start).total_seconds()
    days = max(1, math.ceil(seconds / 86400))
    if listing.rate_unit == RateUnit.PER_HOUR:
        units = Decimal(max(1, math.ceil(seconds / 3600)))
    elif listing.rate_unit == RateUnit.PER_DAY:
        units = Decimal(days)
    elif listing.rate_unit == RateUnit.PER_MONTH:
        units = Decimal(max(1, math.ceil(days / 30)))
    else:  # PER_TONNE_PER_DAY
        units = Decimal(days) * Decimal(quantity or 0)
    return to_cents(listing.rate * units)


def _overlapping_approved(listing, start, end, exclude_id=None):
    qs = EquipmentBooking.objects.filter(listing=listing, status=B.APPROVED, start__lt=end, end__gt=start)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs


def check_availability(listing, start, end, quantity=None, exclude_id=None):
    if end <= start:
        raise ValidationError({"end": ["End must be after start."]})
    overlapping = _overlapping_approved(listing, start, end, exclude_id)
    if listing.is_storage:
        if not quantity or quantity <= 0:
            raise ValidationError({"quantity": ["How many tonnes of storage do you need?"]})
        if listing.capacity is None:
            raise ValidationError("This storage has no capacity set.")
        # Conservative: sum every approved booking that overlaps the window.
        used = overlapping.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
        if used + Decimal(quantity) > listing.capacity:
            free = max(Decimal("0"), listing.capacity - used)
            raise ValidationError(f"Only {free} tonnes of storage are free for those dates.")
    elif overlapping.exists():
        raise ValidationError("This equipment is already booked for part of that time.")


@transaction.atomic
def request_booking(user, *, equipment_id, start, end, quantity=None, notes="", **_ignored) -> EquipmentBooking:
    _require_farmer(user)
    listing = EquipmentListing.objects.select_related("owner").filter(pk=equipment_id, is_available=True).first()
    if listing is None:
        raise NotFound("Equipment not found or not available.")
    if listing.owner_id == user.pk:
        raise ValidationError("You can't book your own equipment.")
    if start < timezone.now():
        raise ValidationError({"start": ["Start can't be in the past."]})
    check_availability(listing, start, end, quantity)
    booking = EquipmentBooking.objects.create(listing=listing, requester=user, start=start, end=end,
                                              quantity=quantity if listing.is_storage else None, notes=notes or "",
                                              estimated_cost=estimate_cost(listing, start, end, quantity))
    notify(listing.owner, "booking_requested", f"{user.display_name} asked to book {listing.name}.",
           f"equipment/bookings/{booking.pk}")
    return booking


@transaction.atomic
def decide(user, booking_id, approve: bool) -> EquipmentBooking:
    booking = EquipmentBooking.objects.select_related("listing", "requester").filter(pk=booking_id).first()
    if booking is None or booking.listing.owner_id != user.pk:
        raise NotFound("Booking not found.")
    if booking.status != B.REQUESTED:
        raise ValidationError("Only requested bookings can be approved or declined.")
    if approve:
        EquipmentListing.objects.select_for_update().get(pk=booking.listing_id)  # serialise approvals
        check_availability(booking.listing, booking.start, booking.end, booking.quantity, exclude_id=booking.pk)
    booking.status = B.APPROVED if approve else B.DECLINED
    booking.save(update_fields=["status", "updated_at"])
    notify(booking.requester, f"booking_{booking.status.lower()}",
           f"Your booking of {booking.listing.name} was {booking.status.lower()}.", f"equipment/bookings/{booking.pk}")
    return booking


@transaction.atomic
def cancel(user, booking_id) -> EquipmentBooking:
    booking = EquipmentBooking.objects.select_related("listing").filter(
        Q(requester=user) | Q(listing__owner=user), pk=booking_id).first()
    if booking is None:
        raise NotFound("Booking not found.")
    if booking.status not in (B.REQUESTED, B.APPROVED):
        raise ValidationError("This booking can't be cancelled.")
    booking.status = B.CANCELLED
    booking.save(update_fields=["status", "updated_at"])
    other = booking.listing.owner if user.pk == booking.requester_id else booking.requester
    notify(other, "booking_cancelled", f"Booking of {booking.listing.name} was cancelled.",
           f"equipment/bookings/{booking.pk}")
    return booking


@transaction.atomic
def complete(user, booking_id) -> EquipmentBooking:
    booking = EquipmentBooking.objects.select_related("listing").filter(pk=booking_id, listing__owner=user).first()
    if booking is None:
        raise NotFound("Booking not found.")
    if booking.status != B.APPROVED:
        raise ValidationError("Only approved bookings can be completed.")
    booking.status = B.COMPLETED
    booking.save(update_fields=["status", "updated_at"])
    return booking


def find_equipment(user, *, equipment_type=None, needed_from=None, needed_until=None, max_distance_km=None,
                   limit=10, **_ignored) -> dict:
    """Available equipment near the user, free in the requested window. AI contract: FindEquipment."""
    from datetime import datetime, time

    _require_farmer(user)
    qs = EquipmentListing.objects.filter(is_available=True).exclude(owner=user).select_related("owner")
    if equipment_type:
        matching = [t for t in EquipmentListing._meta.get_field("type").choices
                    if equipment_type.strip().lower() in (t[0].lower(), t[1].lower())]
        qs = qs.filter(Q(type__in=[t[0] for t in matching]) | Q(name__icontains=equipment_type.strip()))
    me = UserLocation.objects.filter(user=user).first()
    tz = timezone.get_current_timezone()
    window = None
    if needed_from:
        start = timezone.make_aware(datetime.combine(needed_from, time.min), tz)
        end = timezone.make_aware(datetime.combine(needed_until or needed_from, time.max), tz)
        window = (start, end)
    rows = []
    for item in qs[:500]:
        owner_loc = UserLocation.objects.filter(user_id=item.owner_id).first()
        if max_distance_km is not None and not within_km(me, owner_loc, max_distance_km):
            continue
        free_tonnes = None
        if window:
            overlapping = _overlapping_approved(item, *window)
            if item.is_storage:
                used = overlapping.aggregate(total=Sum("quantity"))["total"] or Decimal("0")
                free_tonnes = (item.capacity or Decimal("0")) - used
                if free_tonnes <= 0:
                    continue
            elif overlapping.exists():
                continue
        rows.append((proximity_rank(me, owner_loc), {
            "equipment_id": item.pk,
            "name": item.name,
            "equipment_type": item.type,
            "owner_display_name": item.owner.display_name,
            "rate": float(item.rate),
            "rate_unit": item.rate_unit,
            "capacity_tonnes": float(item.capacity) if item.capacity is not None else None,
            "free_tonnes_in_window": float(free_tonnes) if free_tonnes is not None else None,
            "distance": approximate_distance(me, owner_loc),
            "area": {"town": owner_loc.town, "municipality": owner_loc.municipality,
                     "province": owner_loc.province} if owner_loc else None,
        }))
    rows.sort(key=lambda r: r[0])
    results = [r for _, r in rows[:limit]]
    out = {"available": True, "count": len(results), "results": results}
    if not results:
        out["message"] = "No equipment matches that right now."
    return out
