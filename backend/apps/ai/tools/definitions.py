"""
All tools Grok may call. Each tool's logic lives in a service function
(see ``apps/ai/services_contract.py``); these definitions only declare the
name, description, input schema, roles and confirmation rule.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import Role

from .registry import call_service, register_tool

FARMER = Role.FARMER
BUYER = Role.WHOLESALE_BUYER

UNIT_CHOICES = ["kg", "tonne", "g", "crate", "bag", "box", "bunch", "head", "dozen", "tray", "litre", "unit"]


def max_distance_field():
    return serializers.IntegerField(
        required=False, min_value=1, max_value=2000,
        help_text="Only include results within this straight-line distance in km. Omit for any distance.",
    )


def limit_field():
    return serializers.IntegerField(required=False, min_value=1, max_value=20, default=10,
                                    help_text="Maximum number of results.")


def produce_field(required=True):
    return serializers.CharField(required=required, max_length=80, min_length=2,
                                 help_text="Produce name, e.g. 'potatoes', 'butternut', 'spinach'.")


def _fmt_qty(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


def _fmt_money(value: Decimal) -> str:
    return f"R{value:,.2f}".replace(",", " ")


def _fmt_date(value) -> str:
    return f"{value.day} {value:%b %Y}"


# --- Inputs ------------------------------------------------------------------------------

class FindNearbyFarmersInput(serializers.Serializer):
    max_distance_km = max_distance_field()
    limit = limit_field()


class SearchRecommendedFarmersInput(serializers.Serializer):
    produce = produce_field()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                        help_text="How much the buyer needs.")
    unit = serializers.ChoiceField(choices=UNIT_CHOICES)
    max_distance_km = max_distance_field()
    needed_by = serializers.DateField(required=False, help_text="Date the produce is needed by.")
    limit = limit_field()


class SearchBuyerRequirementsInput(serializers.Serializer):
    produce = produce_field(required=False)
    max_distance_km = max_distance_field()
    limit = limit_field()


class CreateOrUpdateListingInput(serializers.Serializer):
    listing_id = serializers.IntegerField(required=False, min_value=1,
                                          help_text="Only when updating one of the user's existing listings.")
    produce = produce_field()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                        max_value=Decimal("1000000"))
    unit = serializers.ChoiceField(choices=UNIT_CHOICES)
    price_per_unit = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"),
                                              help_text="Price in South African rand (ZAR) per unit.")
    available_from = serializers.DateField(required=False)
    available_until = serializers.DateField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")

    def validate(self, attrs):
        start, end = attrs.get("available_from"), attrs.get("available_until")
        if start and end and end < start:
            raise serializers.ValidationError({"available_until": ["Must be on or after available_from."]})
        return attrs


def summarize_listing(data) -> str:
    verb = f"Update listing #{data['listing_id']}" if data.get("listing_id") else "Create a listing"
    text = (f"{verb}: {_fmt_qty(data['quantity'])} {data['unit']} {data['produce']} "
            f"at {_fmt_money(data['price_per_unit'])}/{data['unit']}")
    if data.get("available_from"):
        text += f", available from {_fmt_date(data['available_from'])}"
    if data.get("available_until"):
        text += f" until {_fmt_date(data['available_until'])}"
    return text


class FindBulkPurchasesInput(serializers.Serializer):
    item = serializers.CharField(required=False, max_length=80,
                                 help_text="What to buy in bulk, e.g. 'fertiliser', 'seed potatoes'.")
    max_distance_km = max_distance_field()
    limit = limit_field()


class CostParticipantInput(serializers.Serializer):
    label = serializers.CharField(max_length=80, help_text="Name of the participant or farm.")
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False,
                                        help_text="Quantity used, needed when split_method is by_quantity.")


class CalculateCostSharesInput(serializers.Serializer):
    total_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                          help_text="Total cost in rand (ZAR).")
    split_method = serializers.ChoiceField(choices=["equal", "by_quantity"])
    participants = CostParticipantInput(many=True, min_length=2, max_length=50)

    def validate(self, attrs):
        if attrs["split_method"] == "by_quantity":
            if any(p.get("quantity") is None for p in attrs["participants"]):
                raise serializers.ValidationError({"participants": ["Every participant needs a quantity."]})
            if sum(p["quantity"] for p in attrs["participants"]) <= 0:
                raise serializers.ValidationError({"participants": ["Total quantity must be more than zero."]})
        return attrs


class FindTransportRequestsInput(serializers.Serializer):
    destination_town = serializers.CharField(required=False, max_length=120)
    travel_date = serializers.DateField(required=False)
    max_distance_km = max_distance_field()
    limit = limit_field()


class FindFarmerGroupsInput(serializers.Serializer):
    focus = serializers.CharField(required=False, max_length=80,
                                  help_text="What the group is about, e.g. 'security', 'poultry', 'irrigation'.")
    max_distance_km = max_distance_field()
    limit = limit_field()


class FindEquipmentInput(serializers.Serializer):
    equipment_type = serializers.CharField(required=False, max_length=80, help_text="e.g. 'tractor', 'baler'.")
    needed_from = serializers.DateField(required=False)
    needed_until = serializers.DateField(required=False)
    max_distance_km = max_distance_field()
    limit = limit_field()

    def validate(self, attrs):
        start, end = attrs.get("needed_from"), attrs.get("needed_until")
        if start and end and end < start:
            raise serializers.ValidationError({"needed_until": ["Must be on or after needed_from."]})
        return attrs


# --- Tools ---------------------------------------------------------------------------------

@register_tool(
    name="find_nearby_farmers",
    description=(
        "Find registered farmers nearest to the current user, nearest first. Returns display "
        "names, town/municipality/province and an approximate straight-line distance. "
        "Does not say what they grow."
    ),
    input_serializer=FindNearbyFarmersInput,
    allowed_roles={FARMER, BUYER},
    service="find_nearby_farmers",
)
def find_nearby_farmers(user, data):
    return call_service("find_nearby_farmers", user, data)


@register_tool(
    name="search_recommended_farmers",
    description=(
        "For a wholesale buyer: find farmers whose current listings best match a produce need "
        "(quantity, unit, distance, date). Results are ranked by the backend and include "
        "match_reasons and any shortfall."
    ),
    input_serializer=SearchRecommendedFarmersInput,
    allowed_roles={BUYER},
    service="search_recommended_farmers",
)
def search_recommended_farmers(user, data):
    return call_service("search_recommended_farmers", user, data)


@register_tool(
    name="search_buyer_requirements",
    description="For a farmer: find wholesale buyers' open produce requirements that match what they could supply.",
    input_serializer=SearchBuyerRequirementsInput,
    allowed_roles={FARMER},
    service="search_buyer_requirements",
)
def search_buyer_requirements(user, data):
    return call_service("search_buyer_requirements", user, data)


@register_tool(
    name="create_or_update_listing",
    description=(
        "Propose creating a new produce listing, or updating one of the farmer's existing "
        "listings. This NEVER saves directly: it prepares the change and the user must "
        "confirm it in the app."
    ),
    input_serializer=CreateOrUpdateListingInput,
    allowed_roles={FARMER},
    requires_confirmation=True,
    summarize=summarize_listing,
    service="create_or_update_listing",
)
def create_or_update_listing(user, data):
    return call_service("create_or_update_listing", user, data)


@register_tool(
    name="find_bulk_purchases",
    description="For a farmer: find open group bulk-buying deals (e.g. fertiliser, seed) they could join.",
    input_serializer=FindBulkPurchasesInput,
    allowed_roles={FARMER},
    service="find_bulk_purchases",
)
def find_bulk_purchases(user, data):
    return call_service("find_bulk_purchases", user, data)


@register_tool(
    name="calculate_cost_shares",
    description=(
        "Split a shared cost (transport, equipment hire, bulk purchase) between participants, "
        "equally or by quantity. Calculation only: nothing is saved or committed."
    ),
    input_serializer=CalculateCostSharesInput,
    allowed_roles={FARMER},
    service="calculate_cost_shares",
)
def calculate_cost_shares(user, data):
    return call_service("calculate_cost_shares", user, data)


@register_tool(
    name="find_transport_requests",
    description="For a farmer: find shared-transport trips or requests they could share a load with.",
    input_serializer=FindTransportRequestsInput,
    allowed_roles={FARMER},
    service="find_transport_requests",
)
def find_transport_requests(user, data):
    return call_service("find_transport_requests", user, data)


@register_tool(
    name="find_farmer_groups",
    description="For a farmer: find nearby farmer groups (co-ops, security groups, study groups) to join.",
    input_serializer=FindFarmerGroupsInput,
    allowed_roles={FARMER},
    service="find_farmer_groups",
)
def find_farmer_groups(user, data):
    return call_service("find_farmer_groups", user, data)


@register_tool(
    name="find_equipment",
    description="For a farmer: find equipment (tractors, implements, etc.) other farmers offer to share or hire out.",
    input_serializer=FindEquipmentInput,
    allowed_roles={FARMER},
    service="find_equipment",
)
def find_equipment(user, data):
    return call_service("find_equipment", user, data)
