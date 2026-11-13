"""
Listing business logic. Used by the API views, the AI tools and the tests.
"""
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from apps.accounts.models import Role

from .models import ListingStatus, ProduceCategory, ProduceListing, QualityGrade
from .units import Unit


def _require_farmer(user):
    if getattr(user, "role", None) != Role.FARMER:
        raise PermissionDenied("Only farmer accounts can manage produce listings.")


def get_own_listing(user, listing_id, *, for_update=False) -> ProduceListing:
    qs = ProduceListing.objects.not_deleted().filter(farmer=user)
    if for_update:
        qs = qs.select_for_update()
    listing = qs.filter(pk=listing_id).first()
    if listing is None:
        raise NotFound("Listing not found.")
    return listing


def _resolve_category(category):
    if category in (None, ""):
        return None
    if isinstance(category, ProduceCategory):
        return category
    found = ProduceCategory.objects.filter(slug=str(category).lower()).first() or \
        ProduceCategory.objects.filter(name__iexact=str(category)).first()
    if found is None:
        raise ValidationError({"category": [f"Unknown category {category!r}."]})
    return found


def listing_summary(listing: ProduceListing) -> dict:
    return {
        "available": True,
        "listing_id": listing.pk,
        "produce": listing.produce_name,
        "quantity": float(listing.quantity_available),
        "unit": listing.unit,
        "price_per_unit": float(listing.price_per_unit),
        "quality_grade": listing.quality_grade,
        "status": listing.status,
        "available_from": listing.available_from.isoformat() if listing.available_from else None,
        "available_until": listing.available_until.isoformat() if listing.available_until else None,
    }


@transaction.atomic
def create_or_update_listing(user, *, produce, quantity, unit, price_per_unit, listing_id=None,
                             available_from=None, available_until=None, notes="", category=None,
                             quality_grade=None, **_ignored) -> dict:
    """
    Create a listing, or update one of ``user``'s own listings when
    ``listing_id`` is given. AI contract: see services_contract.CreateOrUpdateListing.
    """
    _require_farmer(user)
    if unit not in Unit.values:
        raise ValidationError({"unit": [f"Unit must be one of {', '.join(Unit.values)}."]})
    if quality_grade and quality_grade not in QualityGrade.values:
        raise ValidationError({"quality_grade": ["Unknown quality grade."]})

    created = listing_id is None
    listing = ProduceListing(farmer=user) if created else get_own_listing(user, listing_id, for_update=True)
    listing.produce_name = produce.strip()
    listing.quantity_available = quantity
    listing.unit = unit
    listing.price_per_unit = price_per_unit
    if available_from is not None:
        listing.available_from = available_from
    if available_until is not None:
        listing.available_until = available_until
    if listing.available_until and listing.available_from and listing.available_until < listing.available_from:
        raise ValidationError({"available_until": ["Must be on or after available_from."]})
    if notes:
        listing.description = notes
    if category is not None:
        listing.category = _resolve_category(category)
    if quality_grade:
        listing.quality_grade = quality_grade
    if not created and listing.status == ListingStatus.SOLD_OUT and listing.quantity_available > 0:
        listing.status = ListingStatus.ACTIVE
    listing.full_clean(exclude=["farmer", "produce_key"])
    listing.save()
    return {**listing_summary(listing), "created": created}


@transaction.atomic
def set_paused(user, listing_id, paused: bool) -> ProduceListing:
    listing = get_own_listing(user, listing_id, for_update=True)
    if paused:
        if listing.status not in (ListingStatus.ACTIVE, ListingStatus.SOLD_OUT):
            raise ValidationError("Only active listings can be paused.")
        listing.status = ListingStatus.PAUSED
    else:
        if listing.status != ListingStatus.PAUSED:
            raise ValidationError("Only paused listings can be resumed.")
        listing.status = ListingStatus.ACTIVE  # save() turns it into SOLD_OUT if empty
    listing.save()
    return listing


@transaction.atomic
def soft_delete(user, listing_id) -> None:
    listing = get_own_listing(user, listing_id, for_update=True)
    listing.status = ListingStatus.DELETED
    listing.save()
