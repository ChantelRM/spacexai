from decimal import Decimal

from rest_framework import serializers

from apps.listings.models import QualityGrade
from apps.listings.units import Unit
from apps.locations.serializers import PublicLocationSerializer


class FarmerMatchSerializer(serializers.Serializer):
    farmer_id = serializers.IntegerField()
    farmer_display_name = serializers.CharField()
    farm_name = serializers.CharField(allow_null=True)
    is_verified = serializers.BooleanField()
    listing_id = serializers.IntegerField()
    produce = serializers.CharField()
    available_quantity = serializers.FloatField()
    unit = serializers.CharField()
    price_per_unit = serializers.FloatField()
    quality_grade = serializers.CharField()
    available_from = serializers.DateField()
    location = PublicLocationSerializer(allow_null=True)
    score = serializers.IntegerField(help_text="0-100")
    match_reasons = serializers.ListField(child=serializers.CharField())
    gaps = serializers.ListField(child=serializers.CharField())
    shortfall = serializers.CharField(allow_null=True)
    covers_multiple = serializers.BooleanField(required=False)


class FarmerMatchListSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    count = serializers.IntegerField()
    results = FarmerMatchSerializer(many=True)
    message = serializers.CharField(required=False)
    filter_note = serializers.CharField(required=False)


class ItemRecommendationSerializer(FarmerMatchListSerializer):
    produce = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit = serializers.CharField()
    requirement_id = serializers.IntegerField(allow_null=True, required=False)


class MultiSupplierSerializer(serializers.Serializer):
    farmer_id = serializers.IntegerField()
    farmer_display_name = serializers.CharField()
    location = PublicLocationSerializer(allow_null=True)
    produce = serializers.ListField(child=serializers.CharField())


class MultiItemRecommendationSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    items = ItemRecommendationSerializer(many=True)
    covers_multiple = MultiSupplierSerializer(many=True)
    message = serializers.CharField(required=False)


class BuyerMatchSerializer(serializers.Serializer):
    requirement_id = serializers.IntegerField()
    buyer_id = serializers.IntegerField()
    buyer_display_name = serializers.CharField()
    business_name = serializers.CharField(allow_null=True)
    buyer_type = serializers.CharField(allow_null=True)
    produce = serializers.CharField()
    quantity = serializers.FloatField()
    unit = serializers.CharField()
    target_price_per_unit = serializers.FloatField(allow_null=True)
    min_quality_grade = serializers.CharField(allow_null=True)
    needed_by = serializers.DateField()
    recurring = serializers.CharField()
    location = PublicLocationSerializer(allow_null=True)
    your_listing_id = serializers.IntegerField(allow_null=True)
    score = serializers.IntegerField()
    match_reasons = serializers.ListField(child=serializers.CharField())
    gaps = serializers.ListField(child=serializers.CharField())


class BuyerMatchListSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    count = serializers.IntegerField()
    results = BuyerMatchSerializer(many=True)
    message = serializers.CharField(required=False)


class NeedItemSerializer(serializers.Serializer):
    produce = serializers.CharField(max_length=80)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unit = serializers.ChoiceField(choices=Unit.values)


class RecommendFarmersRequestSerializer(serializers.Serializer):
    """Ad hoc buyer criteria. One or more items share the other filters."""

    items = NeedItemSerializer(many=True, min_length=1, max_length=10)
    max_price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False,
                                         help_text="Max price per unit (applies to every item).")
    min_quality = serializers.ChoiceField(choices=QualityGrade.values, required=False)
    needed_by = serializers.DateField(required=False)
    max_distance_km = serializers.IntegerField(min_value=1, max_value=2000, required=False)
    limit = serializers.IntegerField(min_value=1, max_value=20, default=5)
