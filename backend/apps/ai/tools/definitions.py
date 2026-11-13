"""
All tools Grok may call. Each tool's logic lives in a service function
(see ``apps/ai/services_contract.py``); these definitions only declare the
name, description, input schema, roles and confirmation rule.
"""
from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import Role
from apps.listings.models import QualityGrade
from apps.listings.units import Unit, format_quantity

from .registry import call_service, register_tool

FARMER = Role.FARMER
BUYER = Role.WHOLESALE_BUYER

UNIT_CHOICES = Unit.values  # KG, TONNE, BAG, CRATE, BOX, DOZEN, LITRE, UNIT
CATEGORY_SLUGS = ["vegetables", "fruits", "grains", "legumes", "livestock-products", "dairy", "herbs", "other"]


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
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False,
                                         help_text="Maximum price in rand per unit, if the buyer gave one.")
    min_quality = serializers.ChoiceField(choices=QualityGrade.values, required=False)
    max_distance_km = max_distance_field()
    needed_by = serializers.DateField(required=False, help_text="Date the produce is needed by.")
    requirement_id = serializers.IntegerField(required=False, min_value=1,
                                              help_text="Use the criteria of one of the buyer's saved requirements.")
    limit = limit_field()


class SearchBuyerRequirementsInput(serializers.Serializer):
    produce = produce_field(required=False)
    listing_id = serializers.IntegerField(required=False, min_value=1,
                                          help_text="Match buyers for one of the farmer's own listings.")
    max_distance_km = max_distance_field()
    limit = limit_field()


class CreateOrUpdateListingInput(serializers.Serializer):
    listing_id = serializers.IntegerField(required=False, min_value=1,
                                          help_text="Only when updating one of the user's existing listings.")
    produce = produce_field()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                        max_value=Decimal("1000000"))
    unit = serializers.ChoiceField(choices=UNIT_CHOICES)
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                              help_text="Price in South African rand (ZAR) per unit.")
    category = serializers.ChoiceField(choices=CATEGORY_SLUGS, required=False)
    quality_grade = serializers.ChoiceField(choices=QualityGrade.values, required=False)
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
    unit_label = Unit(data["unit"]).label
    text = (f"{verb}: {format_quantity(data['quantity'], data['unit'])} {data['produce']} "
            f"at {_fmt_money(data['price_per_unit'])}/{unit_label}")
    if data.get("quality_grade"):
        text += f", {QualityGrade(data['quality_grade']).label}"
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


# --- Part 3: marketplace and orders ----------------------------------------------------------

class CompareListingsInput(serializers.Serializer):
    listing_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=2, max_length=5,
                                        help_text="IDs of 2-5 listings from earlier results.")


@register_tool(
    name="compare_listings",
    description=("For a buyer: compare 2-5 listings side by side (price, quantity, quality, approximate distance, "
                 "availability and the farmer's order completion record)."),
    input_serializer=CompareListingsInput,
    allowed_roles={BUYER},
    service="compare_listings",
)
def compare_listings(user, data):
    return call_service("compare_listings", user, data)


class OrderLineInput(serializers.Serializer):
    listing_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                        help_text="Quantity in the listing's own unit.")


class CreateOrderInput(serializers.Serializer):
    items = OrderLineInput(many=True, min_length=1, max_length=20)
    delivery_date = serializers.DateField(required=False)
    delivery_notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    buyer_requirement_id = serializers.IntegerField(required=False, min_value=1)

    def validate(self, attrs):
        from apps.orders.services import validate_order_lines

        validate_order_lines(self.context["user"], [dict(i) for i in attrs["items"]])
        return attrs


def summarize_order(data) -> str:
    from apps.listings.models import ProduceListing
    from apps.orders.services import lines_total

    listings = {lst.pk: lst for lst in ProduceListing.objects.select_related("farmer")
                .filter(pk__in=[i["listing_id"] for i in data["items"]])}
    lines = [(listings[i["listing_id"]], Decimal(i["quantity"])) for i in data["items"]]
    parts = [f"{format_quantity(q, lst.unit)} {lst.produce_name} at {_fmt_money(lst.price_per_unit)}/"
             f"{Unit(lst.unit).label} = {_fmt_money((lst.price_per_unit * q).quantize(Decimal('0.01')))}"
             for lst, q in lines]
    text = (f"Place an order with {lines[0][0].farmer.display_name}: " + "; ".join(parts)
            + f". Total {_fmt_money(lines_total(lines))}")
    if data.get("delivery_date"):
        text += f", delivery by {_fmt_date(data['delivery_date'])}"
    return text + ". The farmer must accept it; payment is arranged outside the app."


@register_tool(
    name="create_order",
    description=("For a buyer: prepare an order for listings from ONE farmer. This NEVER places the order "
                 "directly: the buyer must confirm it in the app, then the farmer must accept it."),
    input_serializer=CreateOrderInput,
    allowed_roles={BUYER},
    requires_confirmation=True,
    summarize=summarize_order,
    service="create_order",
)
def create_order(user, data):
    return call_service("create_order", user, data)


class GetMyOrdersInput(serializers.Serializer):
    status = serializers.ChoiceField(choices=["PENDING", "ACCEPTED", "REJECTED", "DISPATCHED", "DELIVERED",
                                              "COMPLETED", "CANCELLED"], required=False)
    limit = limit_field()


@register_tool(
    name="get_my_orders",
    description="List the user's own orders (orders placed for buyers, incoming orders for farmers), newest first.",
    input_serializer=GetMyOrdersInput,
    allowed_roles={FARMER, BUYER},
    service="get_my_orders",
)
def get_my_orders(user, data):
    return call_service("get_my_orders", user, data)


class RespondToOrderInput(serializers.Serializer):
    order_id = serializers.IntegerField(min_value=1)
    decision = serializers.ChoiceField(choices=["accept", "reject"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="",
                                   help_text="Required when rejecting.")

    def validate(self, attrs):
        from apps.orders.models import Order, OrderStatus

        order = Order.objects.filter(pk=attrs["order_id"], farmer=self.context["user"]).first()
        if order is None:
            raise serializers.ValidationError({"order_id": ["Order not found."]})
        if order.status != OrderStatus.PENDING:
            raise serializers.ValidationError({"order_id": ["Only pending orders can be accepted or rejected."]})
        if attrs["decision"] == "reject" and not attrs.get("reason", "").strip():
            raise serializers.ValidationError({"reason": ["Give a reason when rejecting."]})
        return attrs


def summarize_response(data) -> str:
    from apps.orders.models import Order

    order = Order.objects.select_related("buyer").prefetch_related("items").get(pk=data["order_id"])
    items = "; ".join(f"{format_quantity(i.quantity, i.unit)} {i.produce_name}" for i in order.items.all())
    if data["decision"] == "accept":
        return (f"Accept order #{order.pk} from {order.buyer.display_name}: {items} "
                f"({_fmt_money(order.total_amount)} total). The stock will be reserved.")
    return f"Reject order #{order.pk} from {order.buyer.display_name}: {items}. Reason: {data['reason']}"


@register_tool(
    name="respond_to_order",
    description=("For a farmer: prepare accepting or rejecting one of their PENDING incoming orders. Nothing "
                 "happens until the farmer confirms in the app."),
    input_serializer=RespondToOrderInput,
    allowed_roles={FARMER},
    requires_confirmation=True,
    summarize=summarize_response,
    service="respond_to_order",
)
def respond_to_order(user, data):
    return call_service("respond_to_order", user, data)
