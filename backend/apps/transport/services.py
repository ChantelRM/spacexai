"""
Shared transport: organising a trip, joining with a load, splitting the cost.

Split methods (cents rounding, remainder to the largest share, see core.costs):
- WEIGHT / VOLUME / SPACE: proportional to each participant's load.
- EQUAL: equal shares.
- DISTANCE: proportional to each participant's approximate km from their
  pickup point to the destination. GPS haversine when the participant has
  coordinates in their pickup town and the destination has coordinates;
  otherwise the proximity tier estimate (same town 5 km, same municipality
  30 km, same province 150 km, other province 600 km).
- AGREED: the amounts participants agreed; they must sum exactly to the total.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.core.costs import allocate, to_cents
from apps.core.notifications import notify
from apps.locations.distance import _norm, approximate_distance, estimated_km, proximity_rank, within_km
from apps.locations.models import UserLocation

from .models import SplitMethod, TransportParticipant, TransportRequest, TransportStatus

LOAD_FIELD = {SplitMethod.WEIGHT: "load_weight_kg", SplitMethod.VOLUME: "load_volume_m3",
              SplitMethod.SPACE: "load_space_units"}
CAPACITY_FIELD = {"KG": "load_weight_kg", "M3": "load_volume_m3", "SPACES": "load_space_units"}


def _require_farmer(user):
    if getattr(user, "role", None) != Role.FARMER:
        raise PermissionDenied("Shared transport is for farmers.")


def get_request(request_id, *, for_update=False) -> TransportRequest:
    qs = TransportRequest.objects.select_related("organiser")
    if for_update:
        qs = qs.select_for_update()
    tr = qs.filter(pk=request_id).first()
    if tr is None:
        raise NotFound("Transport request not found.")
    return tr


def pickup_area(tr):
    return SimpleNamespace(province=tr.pickup_province, municipality=tr.pickup_municipality, town=tr.pickup_town,
                           latitude=None, longitude=None)


def destination_point(tr):
    return SimpleNamespace(province=tr.destination_province, municipality=tr.destination_municipality,
                           town=tr.destination_town, latitude=tr.destination_latitude,
                           longitude=tr.destination_longitude)


def participant_origin(p, tr):
    """The participant's own location if their pickup is in their home town (GPS stays private), else the area."""
    loc = UserLocation.objects.filter(user_id=p.farmer_id).first()
    town = p.pickup_town or (loc.town if loc else tr.pickup_town)
    if loc and _norm(loc.town) == _norm(town):
        return loc
    return SimpleNamespace(province=tr.pickup_province, municipality=tr.pickup_municipality, town=town,
                           latitude=None, longitude=None)


def compute_shares(tr, participants=None) -> dict:
    """Pure split for a request. Returns {"shares": {participant_id: Decimal|None}, "problem": str|None}."""
    participants = list(participants if participants is not None else tr.participants.all())
    if tr.total_cost is None or not participants:
        return {"shares": {p.pk: None for p in participants}, "problem": "Waiting for a cost quote."
                if tr.total_cost is None else None}
    method = tr.cost_split_method
    if method == SplitMethod.AGREED:
        amounts = [p.agreed_amount for p in participants]
        if any(a is None for a in amounts):
            return {"shares": {p.pk: None for p in participants}, "problem": "Not everyone has an agreed amount yet."}
        total = sum(amounts)
        if to_cents(total) != to_cents(tr.total_cost):
            return {"shares": {p.pk: None for p in participants},
                    "problem": f"Agreed amounts add up to R{to_cents(total)}, but the total is R{to_cents(tr.total_cost)}."}
        return {"shares": {p.pk: to_cents(p.agreed_amount) for p in participants}, "problem": None}
    if method == SplitMethod.EQUAL:
        weights = [1] * len(participants)
    elif method == SplitMethod.DISTANCE:
        dest = destination_point(tr)
        weights = [Decimal(str(round(min(estimated_km(participant_origin(p, tr), dest), 2000), 3)))
                   for p in participants]
    else:
        field = LOAD_FIELD[method]
        weights = [getattr(p, field) or Decimal("0") for p in participants]
    return {"shares": dict(zip([p.pk for p in participants], allocate(tr.total_cost, weights))), "problem": None}


def _recalculate(tr, changed_by=None):
    result = compute_shares(tr)
    for p in tr.participants.all():
        new = result["shares"].get(p.pk)
        if new != p.calculated_share:
            was_confirmed = p.confirmed
            p.calculated_share = new
            p.confirmed, p.confirmed_at = False, None
            p.save(update_fields=["calculated_share", "confirmed", "confirmed_at", "updated_at"])
            if was_confirmed and p.farmer_id != getattr(changed_by, "pk", None):
                notify(p.farmer, "transport_recalculated", f"Your share for the trip to {tr.destination_town} "
                       "changed. Please confirm again.", f"transport/{tr.pk}")
    return result


def _check_load(tr, data):
    field = LOAD_FIELD.get(tr.cost_split_method)
    if field and not data.get(field):
        raise ValidationError({field: ["Needed for this trip's cost split."]})
    if tr.cost_split_method == SplitMethod.AGREED and data.get("agreed_amount") is None and tr.total_cost is not None:
        raise ValidationError({"agreed_amount": ["Enter the amount you agreed to pay."]})


def _check_capacity(tr, extra_participant=None):
    if tr.capacity is None:
        return False
    field = CAPACITY_FIELD.get((tr.capacity_unit or "KG").upper(), "load_weight_kg")
    used = sum((getattr(p, field) or 0) for p in tr.participants.all())
    if used > tr.capacity:
        raise ValidationError(f"Not enough space: the vehicle carries {tr.capacity} {tr.capacity_unit}.")
    return used >= tr.capacity


@transaction.atomic
def create_request(user, *, organiser_load=None, **data) -> TransportRequest:
    _require_farmer(user)
    if data["travel_date"] < timezone.localdate():
        raise ValidationError({"travel_date": ["The travel date can't be in the past."]})
    tr = TransportRequest.objects.create(organiser=user, **data)
    if organiser_load:
        join(user, tr.pk, **organiser_load)
    return tr


@transaction.atomic
def join(user, request_id, **load) -> TransportParticipant:
    _require_farmer(user)
    tr = get_request(request_id, for_update=True)
    if tr.status != TransportStatus.OPEN:
        raise ValidationError("This trip is not open for new loads.")
    if tr.travel_date < timezone.localdate():
        raise ValidationError("This trip has already happened.")
    _check_load(tr, load)
    defaults = {k: load.get(k) for k in ("load_weight_kg", "load_volume_m3", "load_space_units", "agreed_amount")}
    defaults["pickup_town"] = (load.get("pickup_town") or "").strip()
    p, created = TransportParticipant.objects.update_or_create(request=tr, farmer=user, defaults=defaults)
    p.confirmed, p.confirmed_at = False, None
    p.save()
    if _check_capacity(tr):
        tr.status = TransportStatus.FULL
        tr.save(update_fields=["status", "updated_at"])
    _recalculate(tr, user)
    if created and tr.organiser_id != user.pk:
        notify(tr.organiser, "transport_joined", f"{user.display_name} joined your trip to {tr.destination_town}.",
               f"transport/{tr.pk}")
    p.refresh_from_db()
    return p


@transaction.atomic
def leave(user, request_id):
    tr = get_request(request_id, for_update=True)
    if tr.status not in (TransportStatus.OPEN, TransportStatus.FULL):
        raise ValidationError("You can't leave a confirmed trip here; ask the organiser to cancel.")
    if not TransportParticipant.objects.filter(request=tr, farmer=user).delete()[0]:
        raise ValidationError("You haven't joined this trip.")
    if tr.status == TransportStatus.FULL:
        tr.status = TransportStatus.OPEN
        tr.save(update_fields=["status", "updated_at"])
    _recalculate(tr, user)


@transaction.atomic
def update_cost(user, request_id, *, total_cost=None, cost_split_method=None) -> TransportRequest:
    tr = get_request(request_id, for_update=True)
    if tr.organiser_id != user.pk:
        raise PermissionDenied("Only the organiser can set the cost.")
    if tr.status not in (TransportStatus.OPEN, TransportStatus.FULL):
        raise ValidationError("The cost can't change after the trip is confirmed.")
    if total_cost is not None:
        tr.total_cost = total_cost
    if cost_split_method:
        tr.cost_split_method = cost_split_method
    tr.save()
    _recalculate(tr, user)
    return tr


@transaction.atomic
def confirm(user, request_id) -> TransportParticipant:
    tr = get_request(request_id, for_update=True)
    p = TransportParticipant.objects.filter(request=tr, farmer=user).first()
    if p is None:
        raise ValidationError("Join the trip before confirming.")
    if p.calculated_share is None:
        raise ValidationError(compute_shares(tr)["problem"] or "The cost split isn't ready yet.")
    p.confirmed, p.confirmed_at = True, timezone.now()
    p.save(update_fields=["confirmed", "confirmed_at", "updated_at"])
    return p


@transaction.atomic
def set_status(user, request_id, target) -> TransportRequest:
    tr = get_request(request_id, for_update=True)
    if tr.organiser_id != user.pk:
        raise PermissionDenied("Only the organiser can do that.")
    allowed = {TransportStatus.CONFIRMED: [TransportStatus.OPEN, TransportStatus.FULL],
               TransportStatus.COMPLETED: [TransportStatus.CONFIRMED],
               TransportStatus.CANCELLED: [TransportStatus.OPEN, TransportStatus.FULL, TransportStatus.CONFIRMED]}
    if tr.status not in allowed.get(target, []):
        raise ValidationError(f"Can't change a {tr.status.lower()} trip to {target.lower()}.")
    if target == TransportStatus.CONFIRMED:
        if tr.participants.filter(confirmed=False).exists() or not tr.participants.exists():
            raise ValidationError("Every participant must confirm their share first.")
    tr.status = target
    tr.save(update_fields=["status", "updated_at"])
    for p in tr.participants.exclude(farmer=user).select_related("farmer"):
        notify(p.farmer, f"transport_{target.lower()}", f"Trip to {tr.destination_town} is {target.lower()}.",
               f"transport/{tr.pk}")
    return tr


def find_transport_requests(user, *, destination_town=None, travel_date=None, max_distance_km=None, limit=10,
                            **_ignored) -> dict:
    """Open trips ranked by pickup proximity, then destination match, then date closeness. AI contract."""
    _require_farmer(user)
    me = UserLocation.objects.filter(user=user).first()
    qs = TransportRequest.objects.filter(status=TransportStatus.OPEN, travel_date__gte=timezone.localdate())
    rows = []
    for tr in qs.select_related("organiser")[:500]:
        pickup = pickup_area(tr)
        if max_distance_km is not None and not within_km(me, pickup, max_distance_km):
            continue
        wanted = _norm(destination_town)
        dest_match = bool(wanted) and (wanted == _norm(tr.destination_town) or wanted in _norm(tr.destination))
        days_off = abs((tr.travel_date - (travel_date or date.today())).days)
        result = compute_shares(tr)
        rows.append(((proximity_rank(me, pickup), 0 if dest_match else 1, days_off), {
            "transport_request_id": tr.pk,
            "organiser_display_name": tr.organiser.display_name,
            "from_area": {"province": tr.pickup_province, "municipality": tr.pickup_municipality,
                          "town": tr.pickup_town, "distance": approximate_distance(me, pickup)},
            "destination": tr.destination,
            "to_town": tr.destination_town,
            "travel_date": tr.travel_date.isoformat(),
            "vehicle": tr.vehicle_description,
            "total_cost": float(tr.total_cost) if tr.total_cost is not None else None,
            "cost_split_method": tr.cost_split_method,
            "destination_matches": dest_match,
            "participant_count": len(result["shares"]),
            "capacity": f"{tr.capacity} {tr.capacity_unit}" if tr.capacity is not None else None,
        }))
    rows.sort(key=lambda r: r[0])
    results = [r for _, r in rows[:limit]]
    out = {"available": True, "count": len(results), "results": results}
    if not results:
        out["message"] = "No open shared trips match. You can start one in the Co-op hub."
    return out
