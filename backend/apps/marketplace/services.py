"""Marketplace search, comparison and farmer discovery. Privacy-safe representations only."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Count, Q
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Role, User
from apps.farmers.models import FarmerProfile
from apps.listings.models import QualityGrade, ProduceListing, meets_quality
from apps.listings.units import Unit, convert_quantity, produce_key, produce_matches
from apps.locations.distance import proximity_rank, within_km
from apps.locations.models import Province, UserLocation
from apps.locations.serializers import public_location
from apps.recommendations.scoring import farmer_reliability

SORTS = {"price", "-price", "distance", "quantity", "-quantity", "newest"}


def _locations_for(user_ids) -> dict:
    return {loc.user_id: loc for loc in UserLocation.objects.filter(user_id__in=set(user_ids))}


def _profiles_for(user_ids) -> dict:
    return {p.user_id: p for p in FarmerProfile.objects.filter(user_id__in=set(user_ids))}


def public_listing(listing, viewer_loc, farmer_loc, profile=None, request=None) -> dict:
    images = [request.build_absolute_uri(img.image.url) if request else img.image.url
              for img in listing.images.all()]
    return {
        "id": listing.pk,
        "produce_name": listing.produce_name,
        "category": listing.category.slug if listing.category_id else None,
        "category_name": listing.category.name if listing.category_id else None,
        "quantity_available": str(listing.quantity_available),
        "unit": listing.unit,
        "price_per_unit": str(listing.price_per_unit),
        "quality_grade": listing.quality_grade,
        "available_from": listing.available_from,
        "available_until": listing.available_until,
        "description": listing.description,
        "status": listing.status,
        "images": images,
        "farmer": {
            "id": listing.farmer_id,
            "display_name": listing.farmer.display_name,
            "farm_name": profile.farm_name if profile else None,
            "is_verified": bool(profile and profile.is_verified),
        },
        "location": public_location(farmer_loc, viewer_loc),
        "created_at": listing.created_at,
    }


def _decimal(params, name):
    value = params.get(name)
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValidationError({name: ["Enter a number."]})


def search_listings(viewer, params, request=None) -> list[dict]:
    """Active listings matching the filters, sorted. Python-side steps handle units and distance."""
    qs = ProduceListing.objects.active().filter(farmer__is_active=True).select_related(
        "farmer", "category").prefetch_related("images")
    q = (params.get("q") or "").strip()
    key = produce_key(q) if q else ""
    if key:
        qs = qs.filter(produce_key__icontains=key.split()[-1])
    if params.get("category"):
        qs = qs.filter(category__slug=params["category"])
    min_price, max_price = _decimal(params, "min_price"), _decimal(params, "max_price")
    if min_price is not None:
        qs = qs.filter(price_per_unit__gte=min_price)
    if max_price is not None:
        qs = qs.filter(price_per_unit__lte=max_price)
    if params.get("unit"):
        if params["unit"] not in Unit.values:
            raise ValidationError({"unit": ["Unknown unit."]})
    if params.get("province"):
        if params["province"] not in Province.values:
            raise ValidationError({"province": ["Unknown province."]})
        qs = qs.filter(farmer__location__province=params["province"])
    if params.get("municipality"):
        qs = qs.filter(farmer__location__municipality__iexact=params["municipality"].strip())
    if params.get("town"):
        qs = qs.filter(farmer__location__town__iexact=params["town"].strip())
    if params.get("available_by"):
        try:
            qs = qs.filter(available_from__lte=date.fromisoformat(params["available_by"]))
        except ValueError:
            raise ValidationError({"available_by": ["Use YYYY-MM-DD."]})
    if params.get("farmer_id"):
        qs = qs.filter(farmer_id=params["farmer_id"])

    min_quantity = _decimal(params, "min_quantity")
    quality = params.get("quality_grade")
    if quality and quality not in QualityGrade.values:
        raise ValidationError({"quality_grade": ["Unknown quality grade."]})
    max_km = _decimal(params, "max_distance_km")
    sort = params.get("sort") or "newest"
    if sort not in SORTS:
        raise ValidationError({"sort": [f"Use one of {', '.join(sorted(SORTS))}."]})

    listings = list(qs[:2000])
    viewer_loc = UserLocation.objects.filter(user=viewer).first()
    locs = _locations_for(lst.farmer_id for lst in listings)
    profiles = _profiles_for(lst.farmer_id for lst in listings)
    query_unit = params.get("unit")
    rows = []
    for lst in listings:
        if key and not produce_matches(lst.produce_key, key):
            continue
        if quality and not meets_quality(lst.quality_grade, quality):
            continue
        if min_quantity is not None:
            have = convert_quantity(lst.quantity_available, lst.unit, query_unit or lst.unit)
            if have is None or have < min_quantity:
                continue
        elif query_unit and convert_quantity(1, lst.unit, query_unit) is None:
            continue
        farmer_loc = locs.get(lst.farmer_id)
        if max_km is not None and not within_km(viewer_loc, farmer_loc, max_km):
            continue
        rows.append((lst, farmer_loc))

    if sort in ("price", "-price"):
        rows.sort(key=lambda r: r[0].price_per_unit, reverse=sort == "-price")
    elif sort in ("quantity", "-quantity"):
        rows.sort(key=lambda r: convert_quantity(r[0].quantity_available, r[0].unit, Unit.KG) or r[0].quantity_available,
                  reverse=sort == "-quantity")
    elif sort == "distance":
        rows.sort(key=lambda r: proximity_rank(viewer_loc, r[1]))
    else:
        rows.sort(key=lambda r: r[0].created_at, reverse=True)
    return [public_listing(lst, viewer_loc, loc, profiles.get(lst.farmer_id), request) for lst, loc in rows]


def listing_detail(viewer, listing_id, request=None) -> dict:
    lst = (ProduceListing.objects.not_deleted().exclude(status="PAUSED").select_related("farmer", "category")
           .prefetch_related("images").filter(pk=listing_id).first())
    if lst is None:
        raise NotFound("Listing not found.")
    viewer_loc = UserLocation.objects.filter(user=viewer).first()
    farmer_loc = UserLocation.objects.filter(user_id=lst.farmer_id).first()
    return public_listing(lst, viewer_loc, farmer_loc, FarmerProfile.objects.filter(user_id=lst.farmer_id).first(),
                          request)


def compare_listings(viewer, listing_ids, request=None, **_ignored) -> dict:
    """Side-by-side comparison of 2-5 listings (price, quantity, quality, distance, availability, reliability)."""
    ids = []
    for raw in listing_ids:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            raise ValidationError({"listing_ids": ["Listing IDs must be numbers."]})
    ids = list(dict.fromkeys(ids))
    if not 2 <= len(ids) <= 5:
        raise ValidationError({"listing_ids": ["Compare between 2 and 5 listings."]})
    found = {lst.pk: lst for lst in ProduceListing.objects.active().filter(pk__in=ids)
             .select_related("farmer", "category").prefetch_related("images")}
    missing = [i for i in ids if i not in found]
    viewer_loc = UserLocation.objects.filter(user=viewer).first()
    locs = _locations_for(lst.farmer_id for lst in found.values())
    profiles = _profiles_for(lst.farmer_id for lst in found.values())
    rows = []
    for i in ids:
        if i not in found:
            continue
        lst = found[i]
        row = public_listing(lst, viewer_loc, locs.get(lst.farmer_id), profiles.get(lst.farmer_id), request)
        stats = farmer_reliability(lst.farmer)
        row["reliability"] = {
            "completed_orders": stats["completed"],
            "finished_orders": stats["finished"],
            "completion_rate": round(stats["ratio"], 2) if stats["ratio"] is not None else None,
            "note": None if stats["ratio"] is not None else "Not enough orders yet to rate reliability",
        }
        row["available_now"] = lst.available_from <= date.today()
        rows.append(row)
    result = {"available": True, "count": len(rows), "results": rows}
    if rows:
        cheapest = min(rows, key=lambda r: Decimal(r["price_per_unit"]))
        result["cheapest_listing_id"] = cheapest["id"]
        with_km = [r for r in rows if r["location"] and r["location"]["distance"]["km"] is not None]
        if with_km:
            result["nearest_listing_id"] = min(with_km, key=lambda r: r["location"]["distance"]["km"])["id"]
    if missing:
        result["unavailable_listing_ids"] = missing
    return result


def discover_farmers(viewer, params) -> list[dict]:
    qs = User.objects.filter(role=Role.FARMER, is_active=True).exclude(pk=viewer.pk).annotate(
        active_listings=Count("produce_listings", filter=Q(produce_listings__status="ACTIVE",
                                                           produce_listings__quantity_available__gt=0)))
    if params.get("province"):
        qs = qs.filter(location__province=params["province"])
    if params.get("municipality"):
        qs = qs.filter(location__municipality__iexact=params["municipality"].strip())
    if params.get("town"):
        qs = qs.filter(location__town__iexact=params["town"].strip())
    if params.get("verified") in ("true", "1"):
        qs = qs.filter(farmer_profile__is_verified=True)
    farmers = list(qs[:2000])
    produce = (params.get("produce") or "").strip()
    key = produce_key(produce) if produce else ""
    produce_by_farmer = {}
    for lst in ProduceListing.objects.active().filter(farmer__in=farmers).only("farmer_id", "produce_name", "produce_key"):
        produce_by_farmer.setdefault(lst.farmer_id, []).append(lst)
    viewer_loc = UserLocation.objects.filter(user=viewer).first()
    locs = _locations_for(f.pk for f in farmers)
    profiles = _profiles_for(f.pk for f in farmers)
    max_km = _decimal(params, "max_distance_km")
    rows = []
    for f in farmers:
        listings = produce_by_farmer.get(f.pk, [])
        profile = profiles.get(f.pk)
        if key:
            listed = any(produce_matches(lst.produce_key, key) for lst in listings)
            grows = profile and any(produce_matches(produce_key(p), key) for p in profile.main_produce)
            if not (listed or grows):
                continue
        if max_km is not None and not within_km(viewer_loc, locs.get(f.pk), max_km):
            continue
        rows.append((proximity_rank(viewer_loc, locs.get(f.pk)), {
            "farmer_id": f.pk,
            "display_name": f.display_name,
            "farm_name": profile.farm_name if profile else None,
            "is_verified": bool(profile and profile.is_verified),
            "main_produce": profile.main_produce if profile else [],
            "listed_produce": sorted({lst.produce_name for lst in listings}),
            "active_listings_count": f.active_listings,
            "location": public_location(locs.get(f.pk), viewer_loc),
        }))
    rows.sort(key=lambda r: (r[0], r[1]["farmer_id"]))
    return [r for _, r in rows]

