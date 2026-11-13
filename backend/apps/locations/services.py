"""Location services used by the AI agent and other apps."""
from apps.accounts.models import Role

from .distance import proximity_rank, within_km
from .models import UserLocation
from .serializers import public_location

# Upper bound on rows ranked in Python. Fine for SQLite/early growth; replace
# with a bounding-box or PostGIS query when farmer numbers grow.
MAX_CANDIDATES = 5000


def find_nearby_farmers(user, *, max_distance_km=None, limit=10, produce=None, **_ignored) -> dict:
    """
    Farmers nearest to ``user``, nearest first. Works with or without GPS.
    Returns only display name, area names and an approximate distance.
    """
    try:
        origin = user.location
    except UserLocation.DoesNotExist:
        return {
            "available": True,
            "count": 0,
            "results": [],
            "message": "You have not set your location yet, so I can't tell who is near you. "
                       "Add your location in your profile first.",
        }

    candidates = (
        UserLocation.objects.select_related("user")
        .filter(user__role=Role.FARMER, user__is_active=True)
        .exclude(user=user)[:MAX_CANDIDATES]
    )
    candidates = [loc for loc in candidates if within_km(origin, loc, max_distance_km)]
    if produce:
        candidates = [loc for loc in candidates if _grows(loc.user, produce)]
    ranked = sorted(
        candidates,
        key=lambda loc: (proximity_rank(origin, loc), loc.user_id),
    )
    results = [
        {
            "farmer_id": loc.user_id,
            "display_name": loc.user.display_name,
            "location": public_location(loc, origin),
        }
        for loc in ranked[:limit]
    ]
    response = {"available": True, "count": len(results), "results": results}
    if produce:
        response["produce_filter"] = produce
    if not results:
        response["message"] = (
            "No farmers found within that distance." if max_distance_km else "No other farmers have registered a location yet."
        )
    return response


def _grows(farmer, produce) -> bool:
    """True if the farmer lists this produce or names it in their farm profile."""
    from apps.farmers.models import FarmerProfile
    from apps.listings.models import ProduceListing
    from apps.listings.units import produce_key, produce_matches

    key = produce_key(produce)
    if any(produce_matches(k, key) for k in
           ProduceListing.objects.active().filter(farmer=farmer).values_list("produce_key", flat=True)):
        return True
    profile = FarmerProfile.objects.filter(user=farmer).first()
    return bool(profile and any(produce_matches(produce_key(p), key) for p in profile.main_produce))
