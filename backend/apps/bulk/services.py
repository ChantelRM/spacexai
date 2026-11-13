"""
Bulk purchasing. Joining and confirming are separate steps:

- join / change quantity / leave -> everyone's contribution is recalculated;
  any member whose amount changed is un-confirmed and notified.
- confirm -> an explicit commitment to pay the organiser (outside the app).
- lock -> organiser only, and only when every member has confirmed.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.core.notifications import notify
from apps.groups.services import is_active_member
from apps.locations.distance import approximate_distance, proximity_rank, within_km
from apps.locations.models import UserLocation

from .calculations import calculate_cost_shares, split_total
from .models import BulkPurchase, BulkPurchaseMember, BulkStatus


def _require_farmer(user):
    if getattr(user, "role", None) != Role.FARMER:
        raise PermissionDenied("Bulk purchasing is for farmers.")


def get_purchase(user, purchase_id, *, for_update=False) -> BulkPurchase:
    qs = BulkPurchase.objects.select_related("organiser", "group")
    if for_update:
        qs = qs.select_for_update()
    bp = qs.filter(pk=purchase_id).first()
    if bp is None or (bp.group_id and not is_active_member(bp.group, user) and bp.organiser_id != user.pk
                      and not bp.members.filter(farmer=user).exists()):
        raise NotFound("Bulk purchase not found.")
    return bp


def breakdown(bp: BulkPurchase) -> dict:
    members = list(bp.members.select_related("farmer"))
    if not members:
        return {"total_quantity": Decimal("0"), "unit_price": bp.unit_price, "applied_tier": None,
                "goods_total": Decimal("0"), "shared_fees": bp.shared_fees, "total": Decimal("0"),
                "savings": Decimal("0"), "shares": []}
    calc = calculate_cost_shares([{"label": m.farmer.display_name, "quantity": m.quantity} for m in members],
                                 bp.unit_price, bp.discount_tiers, bp.shared_fees)
    for share, m in zip(calc["shares"], members):
        share["farmer_id"] = m.farmer_id
        share["confirmed"] = m.confirmed
    return calc


def _recalculate(bp: BulkPurchase, changed_by=None):
    members = list(bp.members.select_related("farmer"))
    if not members:
        return
    calc = calculate_cost_shares([{"label": m.farmer_id, "quantity": m.quantity} for m in members],
                                 bp.unit_price, bp.discount_tiers, bp.shared_fees)
    for m, share in zip(members, calc["shares"]):
        new_amount = share["share_amount"]
        if new_amount != m.calculated_contribution:
            was_confirmed = m.confirmed
            m.calculated_contribution = new_amount
            m.confirmed, m.confirmed_at = False, None
            m.save(update_fields=["calculated_contribution", "confirmed", "confirmed_at", "updated_at"])
            if was_confirmed and m.farmer_id != getattr(changed_by, "pk", None):
                notify(m.farmer, "bulk_recalculated",
                       f"Your share of {bp.item_name} changed to R{new_amount}. Please confirm again.",
                       f"bulk/{bp.pk}")


def _require_open(bp):
    if bp.status != BulkStatus.OPEN:
        raise ValidationError("This bulk purchase is no longer open.")


@transaction.atomic
def create_purchase(user, **data) -> BulkPurchase:
    _require_farmer(user)
    group = data.get("group")
    if group and not is_active_member(group, user):
        raise PermissionDenied("You can only organise a bulk purchase for a group you belong to.")
    if data["deadline"] < timezone.localdate():
        raise ValidationError({"deadline": ["The deadline can't be in the past."]})
    quantity = data.pop("organiser_quantity", None)
    bp = BulkPurchase.objects.create(organiser=user, **data)
    if quantity:
        BulkPurchaseMember.objects.create(bulk_purchase=bp, farmer=user, quantity=quantity)
        _recalculate(bp, user)
    return bp


@transaction.atomic
def join(user, purchase_id, quantity) -> BulkPurchaseMember:
    _require_farmer(user)
    bp = get_purchase(user, purchase_id, for_update=True)
    _require_open(bp)
    if bp.deadline < timezone.localdate():
        raise ValidationError("The deadline for this bulk purchase has passed.")
    quantity = Decimal(str(quantity))
    if quantity <= 0:
        raise ValidationError({"quantity": ["Quantity must be more than zero."]})
    member, created = BulkPurchaseMember.objects.get_or_create(bulk_purchase=bp, farmer=user,
                                                               defaults={"quantity": quantity})
    if not created:
        member.quantity = quantity
        member.confirmed, member.confirmed_at = False, None
        member.save()
    _recalculate(bp, user)
    if created and bp.organiser_id != user.pk:
        notify(bp.organiser, "bulk_joined", f"{user.display_name} joined {bp.item_name} ({quantity} {bp.unit}).",
               f"bulk/{bp.pk}")
    member.refresh_from_db()
    return member


@transaction.atomic
def leave(user, purchase_id):
    bp = get_purchase(user, purchase_id, for_update=True)
    _require_open(bp)
    deleted, _ = BulkPurchaseMember.objects.filter(bulk_purchase=bp, farmer=user).delete()
    if not deleted:
        raise ValidationError("You haven't joined this bulk purchase.")
    _recalculate(bp, user)


@transaction.atomic
def confirm(user, purchase_id) -> BulkPurchaseMember:
    """Explicit commitment to pay your calculated contribution (settled outside the app)."""
    bp = get_purchase(user, purchase_id, for_update=True)
    _require_open(bp)
    member = BulkPurchaseMember.objects.filter(bulk_purchase=bp, farmer=user).first()
    if member is None:
        raise ValidationError("Join the bulk purchase before confirming.")
    member.confirmed, member.confirmed_at = True, timezone.now()
    member.save(update_fields=["confirmed", "confirmed_at", "updated_at"])
    return member


@transaction.atomic
def set_status(user, purchase_id, target) -> BulkPurchase:
    bp = get_purchase(user, purchase_id, for_update=True)
    if bp.organiser_id != user.pk:
        raise PermissionDenied("Only the organiser can do that.")
    allowed = {
        BulkStatus.LOCKED: [BulkStatus.OPEN],
        BulkStatus.ORDERED: [BulkStatus.LOCKED],
        BulkStatus.COMPLETED: [BulkStatus.ORDERED],
        BulkStatus.CANCELLED: [BulkStatus.OPEN, BulkStatus.LOCKED],
    }
    if bp.status not in allowed.get(target, []):
        raise ValidationError(f"Can't change a {bp.status.lower()} bulk purchase to {target.lower()}.")
    if target == BulkStatus.LOCKED:
        members = bp.members.all()
        if not members.exists():
            raise ValidationError("Nobody has joined yet.")
        unconfirmed = members.filter(confirmed=False).count()
        if unconfirmed:
            raise ValidationError(f"{unconfirmed} member(s) haven't confirmed their contribution yet.")
    bp.status = target
    bp.save(update_fields=["status", "updated_at"])
    for m in bp.members.exclude(farmer=user).select_related("farmer"):
        notify(m.farmer, f"bulk_{target.lower()}", f"{bp.item_name} is now {bp.get_status_display().lower()}.",
               f"bulk/{bp.pk}")
    return bp


@transaction.atomic
def update_terms(user, purchase_id, **changes) -> BulkPurchase:
    """Organiser edits price, tiers or fees while OPEN: everyone is recalculated."""
    bp = get_purchase(user, purchase_id, for_update=True)
    if bp.organiser_id != user.pk:
        raise PermissionDenied("Only the organiser can change the terms.")
    _require_open(bp)
    for field, value in changes.items():
        setattr(bp, field, value)
    bp.save()
    _recalculate(bp, user)
    return bp


def visible_purchases(user):
    from django.db.models import Q

    return BulkPurchase.objects.filter(
        Q(group__isnull=True) | Q(group__memberships__farmer=user, group__memberships__status="ACTIVE")
        | Q(organiser=user) | Q(members__farmer=user)).distinct()


def _origin_of(bp):
    return UserLocation.objects.filter(user_id=bp.organiser_id).first()


def find_bulk_purchases(user, *, item=None, category=None, max_distance_km=None, limit=10, **_ignored) -> dict:
    """Open, joinable purchases near the user. AI contract: FindBulkPurchases."""
    _require_farmer(user)
    qs = visible_purchases(user).filter(status=BulkStatus.OPEN, deadline__gte=timezone.localdate())
    if item:
        from django.db.models import Q

        qs = qs.filter(Q(item_name__icontains=item.strip()) | Q(description__icontains=item.strip()))
    if category:
        qs = qs.filter(category=category)
    me = UserLocation.objects.filter(user=user).first()
    rows = []
    for bp in qs.select_related("organiser")[:500]:
        origin = _origin_of(bp)
        if max_distance_km is not None and not within_km(me, origin, max_distance_km):
            continue
        calc = breakdown(bp)
        mine = next((s for s in calc["shares"] if s["farmer_id"] == user.pk), None)
        rows.append((proximity_rank(me, origin), {
            "bulk_purchase_id": bp.pk,
            "title": bp.item_name,
            "item": bp.item_name,
            "category": bp.category,
            "organiser_display_name": bp.organiser.display_name,
            "group_id": bp.group_id,
            "unit": bp.unit,
            "base_unit_price": float(bp.unit_price),
            "current_unit_price": float(calc["unit_price"]),
            "quantity_committed": float(calc["total_quantity"]),
            "member_count": len(calc["shares"]),
            "discount_tiers": bp.discount_tiers,
            "deadline": bp.deadline.isoformat(),
            "distance": approximate_distance(me, origin),
            "my_quantity": float(mine["quantity"]) if mine else None,
            "my_contribution": float(mine["share_amount"]) if mine else None,
        }))
    rows.sort(key=lambda r: (r[0], r[1]["deadline"]))
    results = [r for _, r in rows[:limit]]
    out = {"available": True, "count": len(results), "results": results}
    if not results:
        out["message"] = "No open bulk purchases match. You can start one in the Co-op hub."
    return out


def calculate_cost_shares_for_ai(user, *, total_cost=None, split_method="by_quantity", participants=None,
                                 bulk_purchase_id=None, **_ignored) -> dict:
    """Calculation only (never saves). AI contract: CalculateCostShares."""
    _require_farmer(user)
    if bulk_purchase_id:
        bp = get_purchase(user, bulk_purchase_id)
        calc = breakdown(bp)
        return {
            "available": True, "bulk_purchase_id": bp.pk, "item": bp.item_name, "unit": bp.unit,
            "total_quantity": float(calc["total_quantity"]), "unit_price": float(calc["unit_price"]),
            "applied_tier": calc["applied_tier"], "shared_fees": float(calc["shared_fees"]),
            "total_cost": float(calc["total"]), "savings": float(calc["savings"]), "split_method": "by_quantity",
            "shares": [{"label": s["label"], "quantity": float(s["quantity"]), "share_amount": float(s["share_amount"]),
                        "share_percent": s["share_percent"], "confirmed": s["confirmed"]} for s in calc["shares"]],
        }
    if total_cost is None or not participants:
        raise ValidationError("Give either bulk_purchase_id, or total_cost with participants.")
    return split_total(total_cost, participants, split_method)
