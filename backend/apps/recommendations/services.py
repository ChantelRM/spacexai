"""
Recommendation engine: buyer → farmers and farmer → buyers.

Hard filters decide who is eligible; ``scoring`` ranks and explains. Every
run is logged in RecommendationLog. Results never include contact details
or coordinates.
"""
from __future__ import annotations

from decimal import Decimal

from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role
from apps.buyers.models import BuyerRequirement, RequirementStatus
from apps.farmers.models import FarmerProfile
from apps.listings.models import ProduceListing
from apps.listings.units import Unit, convert_quantity, produce_key, produce_matches, units_compatible
from apps.locations.distance import _norm, within_km
from apps.locations.models import UserLocation
from apps.locations.serializers import public_location

from . import scoring
from .models import RecommendationLog

Direction = RecommendationLog.Direction


def _location(user):
    return UserLocation.objects.filter(user=user).first()


def _in_areas(location, areas) -> bool:
    if location is None:
        return False
    for area in areas or []:
        if area.get("province") != location.province:
            continue
        if area.get("municipality") and _norm(area["municipality"]) != _norm(location.municipality):
            continue
        if area.get("town") and _norm(area["town"]) != _norm(location.town):
            continue
        return True
    return False


def _log(user, direction, source, criteria, results, id_key):
    RecommendationLog.objects.create(
        user=user, direction=direction, source=source,
        criteria={k: (str(v) if v is not None and not isinstance(v, (int, float, str, bool, list, dict)) else v)
                  for k, v in criteria.items()},
        results=[{"id": r[id_key], "score": r["score"]} for r in results],
    )


def _candidate_listings(key):
    last_word = key.split()[-1] if key else ""
    qs = (ProduceListing.objects.active().filter(produce_key__icontains=last_word, farmer__is_active=True,
                                                 farmer__role=Role.FARMER)
          .select_related("farmer"))
    return [listing for listing in qs if produce_matches(listing.produce_key, key)]


# --- Buyer → farmers -------------------------------------------------------------------

def _rank_farmers(user, *, produce, quantity, unit, max_price=None, min_quality=None, needed_by=None,
                  max_distance_km=None, delivery_areas=None):
    key = produce_key(produce)
    if not key:
        raise ValidationError({"produce": ["Enter a produce name."]})
    if unit not in Unit.values:
        raise ValidationError({"unit": [f"Unit must be one of {', '.join(Unit.values)}."]})
    quantity = Decimal(quantity)
    max_price = Decimal(max_price) if max_price is not None else None
    origin = _location(user)

    eligible = []
    for listing in _candidate_listings(key):
        if listing.farmer_id == user.pk or not units_compatible(listing.unit, unit):
            continue
        if needed_by and listing.available_from > needed_by:
            continue
        farmer_loc = _location(listing.farmer)
        if max_distance_km is not None:
            if not within_km(origin, farmer_loc, max_distance_km):
                continue
        elif delivery_areas and not _in_areas(farmer_loc, delivery_areas):
            continue
        available = convert_quantity(listing.quantity_available, listing.unit, unit)
        unit_price = scoring.price_per(listing.price_per_unit, listing.unit, unit)
        if available is None or available <= 0 or unit_price is None:
            continue
        eligible.append((listing, farmer_loc, available, unit_price))

    median_price = scoring.median_or_none([p for *_, p in eligible])
    reliability_cache = {}
    matches = []
    for listing, farmer_loc, available, unit_price in eligible:
        if listing.farmer_id not in reliability_cache:
            reliability_cache[listing.farmer_id] = scoring.farmer_reliability(listing.farmer)
        parts = [
            scoring.score_quantity(available, quantity, unit),
            scoring.score_price(unit_price, unit, median_price, max_price),
            scoring.score_timing(listing.available_from, needed_by),
            scoring.score_quality(listing.quality_grade, min_quality or None),
            scoring.score_reliability(reliability_cache[listing.farmer_id]),
        ]
        d_points, distance, d_reasons, d_gaps = scoring.score_distance(origin, farmer_loc)
        points = sum(p for p, _, _ in parts) + d_points
        reasons = parts[0][1] + d_reasons + parts[1][1] + parts[2][1] + parts[3][1] + parts[4][1]
        gaps = parts[0][2] + d_gaps + parts[1][2] + parts[2][2] + parts[3][2]
        shortfall = next((g for g in parts[0][2]), None)
        profile = FarmerProfile.objects.filter(user=listing.farmer).first()
        matches.append({
            "farmer_id": listing.farmer_id,
            "farmer_display_name": listing.farmer.display_name,
            "farm_name": profile.farm_name if profile else None,
            "is_verified": bool(profile and profile.is_verified),
            "listing_id": listing.pk,
            "produce": listing.produce_name,
            "available_quantity": float(listing.quantity_available),
            "unit": listing.unit,
            "price_per_unit": float(listing.price_per_unit),
            "quality_grade": listing.quality_grade,
            "available_from": listing.available_from.isoformat(),
            "location": public_location(farmer_loc, origin),
            "score": int(round(points)),
            "match_reasons": reasons,
            "gaps": gaps,
            "shortfall": shortfall,
        })
    matches.sort(key=lambda m: (-m["score"], m["price_per_unit"], m["listing_id"]))
    return matches


def search_recommended_farmers(user, *, produce, quantity, unit, max_price=None, min_quality=None,
                               needed_by=None, max_distance_km=None, requirement_id=None, limit=10,
                               source="ai", **_ignored) -> dict:
    """Ranked farmers for one produce need. AI contract: services_contract.SearchRecommendedFarmers."""
    if getattr(user, "role", None) != Role.WHOLESALE_BUYER:
        raise PermissionDenied("Only wholesale buyers can search for recommended farmers.")
    delivery_areas = None
    if requirement_id:
        req = BuyerRequirement.objects.filter(pk=requirement_id, buyer=user).first()
        if req is None:
            raise NotFound("Requirement not found.")
        max_price = max_price if max_price is not None else req.max_price_per_unit
        min_quality = min_quality or req.min_quality_grade or None
        needed_by = needed_by or req.needed_by
        max_distance_km = max_distance_km if max_distance_km is not None else req.max_distance_km
    if max_distance_km is None:
        loc = _location(user)
        delivery_areas = (loc.preferred_delivery_areas if loc else None) or None
    matches = _rank_farmers(user, produce=produce, quantity=quantity, unit=unit, max_price=max_price,
                            min_quality=min_quality, needed_by=needed_by, max_distance_km=max_distance_km,
                            delivery_areas=delivery_areas)[:limit]
    _log(user, Direction.BUYER_TO_FARMER, source,
         {"produce": produce, "quantity": quantity, "unit": unit, "max_price": max_price, "min_quality": min_quality,
          "needed_by": needed_by, "max_distance_km": max_distance_km, "requirement_id": requirement_id},
         matches, "listing_id")
    result = {"available": True, "count": len(matches), "results": matches}
    if not matches:
        result["message"] = f"No farmers currently have {produce} available that match these criteria."
    if delivery_areas:
        result["filter_note"] = "Limited to farmers in your preferred delivery areas."
    return result


def recommend_farmers_for_items(user, items: list[dict], *, source="api", limit=5, **common) -> dict:
    """
    Multi-item need, e.g. [{produce: Tomatoes, quantity: 100, unit: KG}, {produce: Potatoes, ...}].
    Returns ranked farmers per item plus farmers who can supply several items.
    """
    per_item, supplies = [], {}
    for item in items:
        res = search_recommended_farmers(user, source=source, limit=limit, **common, **item)
        per_item.append({**{k: item.get(k) for k in ("produce", "quantity", "unit", "requirement_id")}, **res})
        for match in res["results"]:
            entry = supplies.setdefault(match["farmer_id"], {
                "farmer_id": match["farmer_id"], "farmer_display_name": match["farmer_display_name"],
                "location": match["location"], "produce": [],
            })
            if match["produce"] not in entry["produce"]:
                entry["produce"].append(match["produce"])
    covers_multiple = [e for e in supplies.values() if len(e["produce"]) > 1]
    for item in per_item:
        for match in item["results"]:
            match["covers_multiple"] = match["farmer_id"] in {e["farmer_id"] for e in covers_multiple}
    return {"available": True, "items": per_item, "covers_multiple": covers_multiple}


def dashboard_farmers_for_buyer(user, limit=5) -> dict:
    """Recommendations for each of the buyer's OPEN requirements (dashboard)."""
    reqs = BuyerRequirement.objects.filter(buyer=user, status=RequirementStatus.OPEN).order_by("needed_by")[:10]
    items = [{"produce": r.produce_name, "quantity": r.quantity_needed, "unit": r.unit, "requirement_id": r.pk}
             for r in reqs]
    if not items:
        return {"available": True, "items": [], "covers_multiple": [],
                "message": "Post a requirement to get farmer recommendations."}
    return recommend_farmers_for_items(user, items, source="dashboard", limit=limit)


# --- Farmer → buyers -------------------------------------------------------------------

def search_buyer_requirements(user, *, produce=None, listing_id=None, max_distance_km=None, limit=10,
                              source="ai", **_ignored) -> dict:
    """Open buyer requirements that this farmer could supply, ranked. AI contract: SearchBuyerRequirements."""
    from django.utils import timezone

    if getattr(user, "role", None) != Role.FARMER:
        raise PermissionDenied("Only farmers can search buyer requirements.")
    listings = ProduceListing.objects.active().filter(farmer=user)
    if listing_id:
        listings = ProduceListing.objects.not_deleted().filter(farmer=user, pk=listing_id)
        if not listings.exists():
            raise NotFound("Listing not found.")
    listings = list(listings)
    key = produce_key(produce) if produce else None
    if key:
        listings = [lst for lst in listings if produce_matches(lst.produce_key, key)]

    origin = _location(user)
    today = timezone.localdate()
    reqs = (BuyerRequirement.objects.filter(status=RequirementStatus.OPEN, needed_by__gte=today,
                                            buyer__is_active=True)
            .select_related("buyer", "buyer__buyer_profile"))
    if key:
        reqs = reqs.filter(produce_key__icontains=key.split()[-1])

    matches = []
    for req in reqs:
        if key and not produce_matches(req.produce_key, key):
            continue
        listing = next((lst for lst in listings if produce_matches(lst.produce_key, req.produce_key)
                        and units_compatible(lst.unit, req.unit)), None)
        if listing is None and not key:
            continue  # only produce the farmer actually lists, unless they asked about a produce
        buyer_loc = _location(req.buyer)
        if req.max_distance_km and not within_km(buyer_loc, origin, req.max_distance_km):
            continue
        if max_distance_km is not None and not within_km(origin, buyer_loc, max_distance_km):
            continue

        reasons, gaps, points = [], [], 0.0
        d_points, distance, d_reasons, d_gaps = scoring.score_distance(origin, buyer_loc)
        points += d_points
        if listing is not None:
            available = convert_quantity(listing.quantity_available, listing.unit, req.unit) or Decimal("0")
            unit_price = scoring.price_per(listing.price_per_unit, listing.unit, req.unit)
            for p, r, g in (
                scoring.score_quantity(available, req.quantity_needed, req.unit, supplier_view=True),
                scoring.score_price(unit_price, req.unit, None, req.max_price_per_unit),
                scoring.score_timing(listing.available_from, req.needed_by, supplier_view=True),
                scoring.score_quality(listing.quality_grade, req.min_quality_grade or None),
            ):
                points += p
                reasons += r
                gaps += g
        else:
            gaps.append(f"You have no active listing for {req.produce_name}")
        reasons += d_reasons
        gaps += d_gaps
        areas = buyer_loc.preferred_delivery_areas if buyer_loc else []
        if areas:
            if _in_areas(origin, areas):
                reasons.append("You are in their preferred delivery area")
            else:
                gaps.append("Outside their preferred delivery areas")
        points += scoring.weights()["reliability"] * 0.5  # buyers aren't rated yet: neutral
        profile = getattr(req.buyer, "buyer_profile", None)
        matches.append({
            "requirement_id": req.pk,
            "buyer_id": req.buyer_id,
            "buyer_display_name": req.buyer.display_name,
            "business_name": profile.business_name if profile else None,
            "buyer_type": profile.business_type if profile else None,
            "produce": req.produce_name,
            "quantity": float(req.quantity_needed),
            "unit": req.unit,
            "target_price_per_unit": float(req.max_price_per_unit) if req.max_price_per_unit is not None else None,
            "min_quality_grade": req.min_quality_grade or None,
            "needed_by": req.needed_by.isoformat(),
            "recurring": req.recurring,
            "location": public_location(buyer_loc, origin),
            "your_listing_id": listing.pk if listing else None,
            "score": int(round(points)),
            "match_reasons": reasons,
            "gaps": gaps,
        })
    matches.sort(key=lambda m: (-m["score"], m["needed_by"], m["requirement_id"]))
    matches = matches[:limit]
    _log(user, Direction.FARMER_TO_BUYER, source,
         {"produce": produce, "listing_id": listing_id, "max_distance_km": max_distance_km}, matches,
         "requirement_id")
    result = {"available": True, "count": len(matches), "results": matches}
    if not matches:
        result["message"] = ("No open buyer requirements match your listings right now." if not produce
                             else f"No open buyer requirements for {produce} right now.")
    return result
