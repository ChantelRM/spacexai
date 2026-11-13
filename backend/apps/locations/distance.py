"""
Distance helpers. Straight-line ("as the crow flies") distances only; this is
not driving distance and there is no maps integration.

Use these everywhere you need "near me" so every app ranks the same way:

    from apps.locations.distance import approximate_distance, proximity_rank

    farmers.sort(key=lambda f: proximity_rank(me.location, f.location))
    approximate_distance(me.location, f.location)
    # {"km": 12, "basis": "gps", "label": "≈ 12 km"}
    # {"km": None, "basis": "same_municipality", "label": "Same municipality"}

Arguments may be ``UserLocation`` instances or ``None`` (no location saved).
"""
import math

EARTH_RADIUS_KM = 6371.0088

BASIS_GPS = "gps"
BASIS_SAME_TOWN = "same_town"
BASIS_SAME_MUNICIPALITY = "same_municipality"
BASIS_SAME_PROVINCE = "same_province"
BASIS_DIFFERENT_PROVINCE = "different_province"
BASIS_UNKNOWN = "unknown"  # one side has no saved location

_LABELS = {
    BASIS_SAME_TOWN: "Same town",
    BASIS_SAME_MUNICIPALITY: "Same municipality",
    BASIS_SAME_PROVINCE: "Same province",
    BASIS_DIFFERENT_PROVINCE: "Different province",
    BASIS_UNKNOWN: "Distance unknown",
}

# Rough straight-line distance assumed for each tier when GPS is missing.
# Used only for sorting so GPS and non-GPS results can be ranked together.
TIER_ESTIMATE_KM = {
    BASIS_SAME_TOWN: 5.0,
    BASIS_SAME_MUNICIPALITY: 30.0,
    BASIS_SAME_PROVINCE: 150.0,
    BASIS_DIFFERENT_PROVINCE: 600.0,
    BASIS_UNKNOWN: math.inf,
}


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points in degrees."""
    lat1, lon1, lat2, lon2 = (math.radians(float(v)) for v in (lat1, lon1, lat2, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _norm(value) -> str:
    return " ".join((value or "").split()).casefold()


def _has_coords(loc) -> bool:
    return loc is not None and loc.latitude is not None and loc.longitude is not None


def proximity_tier(loc_a, loc_b) -> str:
    """Administrative-area tier, ignoring GPS."""
    if loc_a is None or loc_b is None:
        return BASIS_UNKNOWN
    if loc_a.province != loc_b.province:
        return BASIS_DIFFERENT_PROVINCE
    if _norm(loc_a.municipality) != _norm(loc_b.municipality):
        return BASIS_SAME_PROVINCE
    if _norm(loc_a.town) != _norm(loc_b.town):
        return BASIS_SAME_MUNICIPALITY
    return BASIS_SAME_TOWN


def rounded_km(km: float) -> int:
    """Round to the nearest km, but never report 0 (that would imply 'same spot')."""
    return max(1, int(round(km)))


def approximate_distance(loc_a, loc_b) -> dict:
    """
    Privacy-safe distance description between two locations.

    Returns ``{"km": int, "basis": "gps", "label": "≈ N km"}`` when both have
    coordinates, otherwise ``{"km": None, "basis": <tier>, "label": ...}`` where
    tier is same_town / same_municipality / same_province /
    different_province / unknown.
    """
    if _has_coords(loc_a) and _has_coords(loc_b):
        km = rounded_km(haversine_km(loc_a.latitude, loc_a.longitude, loc_b.latitude, loc_b.longitude))
        return {"km": km, "basis": BASIS_GPS, "label": f"≈ {km} km"}
    tier = proximity_tier(loc_a, loc_b)
    return {"km": None, "basis": tier, "label": _LABELS[tier]}


def estimated_km(loc_a, loc_b) -> float:
    """Exact km with GPS, otherwise the tier estimate (inf if unknown)."""
    if _has_coords(loc_a) and _has_coords(loc_b):
        return haversine_km(loc_a.latitude, loc_a.longitude, loc_b.latitude, loc_b.longitude)
    return TIER_ESTIMATE_KM[proximity_tier(loc_a, loc_b)]


def proximity_rank(loc_a, loc_b) -> tuple:
    """
    Sort key (smaller = nearer) that works with or without GPS.

    Primary: estimated km (GPS if both sides have it, else the tier estimate).
    Secondary: administrative tier, so on ties a closer tier wins.
    Tertiary: GPS before non-GPS.
    """
    tier = proximity_tier(loc_a, loc_b)
    tier_order = list(TIER_ESTIMATE_KM).index(tier)
    has_gps = _has_coords(loc_a) and _has_coords(loc_b)
    return (estimated_km(loc_a, loc_b), tier_order, 0 if has_gps else 1)


def within_km(loc_a, loc_b, max_km) -> bool:
    """
    True if ``loc_b`` is (probably) within ``max_km`` of ``loc_a``.

    Uses GPS when available. Without GPS, a tier counts as within range when
    its estimate is <= max_km (so same town/municipality usually pass, other
    provinces do not).
    """
    if max_km is None:
        return True
    return estimated_km(loc_a, loc_b) <= float(max_km)
