from django.contrib.auth import get_user_model
from rest_framework.exceptions import NotFound

from apps.accounts.models import Role
from apps.listings.models import ProduceListing
from apps.locations.models import UserLocation
from apps.locations.serializers import public_location


def location_of(user):
    return UserLocation.objects.filter(user=user).first() if user else None


def completed_orders_count(farmer) -> int:
    from django.apps import apps

    if not apps.is_installed("apps.orders"):
        return 0
    from apps.orders.models import Order, OrderStatus

    return Order.objects.filter(farmer=farmer, status=OrderStatus.COMPLETED).count()


def public_farmer_profile(viewer, farmer_id) -> dict:
    """What any signed-in user may see about a farmer. Never contact details or coordinates."""
    farmer = (get_user_model().objects.filter(pk=farmer_id, role=Role.FARMER, is_active=True)
              .select_related("farmer_profile").first())
    if farmer is None:
        raise NotFound("Farmer not found.")
    profile = getattr(farmer, "farmer_profile", None)
    return {
        "farmer_id": farmer.pk,
        "display_name": farmer.display_name,
        "farm_name": profile.farm_name if profile else None,
        "bio": profile.bio if profile else "",
        "farm_size_hectares": profile.farm_size_hectares if profile else None,
        "main_produce": profile.main_produce if profile else [],
        "is_verified": bool(profile and profile.is_verified),
        "location": public_location(location_of(farmer), location_of(viewer)),
        "active_listings_count": ProduceListing.objects.active().filter(farmer=farmer).count(),
        "completed_orders_count": completed_orders_count(farmer),
    }
