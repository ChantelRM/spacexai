"""Response schemas for the marketplace (documents the dicts built in services.py)."""
from rest_framework import serializers

from apps.locations.serializers import PublicLocationSerializer


class ListingFarmerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()
    farm_name = serializers.CharField(allow_null=True)
    is_verified = serializers.BooleanField()


class PublicListingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    produce_name = serializers.CharField()
    category = serializers.CharField(allow_null=True)
    category_name = serializers.CharField(allow_null=True)
    quantity_available = serializers.DecimalField(max_digits=12, decimal_places=2)
    unit = serializers.CharField()
    price_per_unit = serializers.DecimalField(max_digits=12, decimal_places=2)
    quality_grade = serializers.CharField()
    available_from = serializers.DateField()
    available_until = serializers.DateField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    images = serializers.ListField(child=serializers.CharField())
    farmer = ListingFarmerSerializer()
    location = PublicLocationSerializer(allow_null=True)
    created_at = serializers.DateTimeField()


class ReliabilitySerializer(serializers.Serializer):
    completed_orders = serializers.IntegerField()
    finished_orders = serializers.IntegerField()
    completion_rate = serializers.FloatField(allow_null=True)
    note = serializers.CharField(allow_null=True)


class ComparedListingSerializer(PublicListingSerializer):
    reliability = ReliabilitySerializer()
    available_now = serializers.BooleanField()


class CompareResponseSerializer(serializers.Serializer):
    available = serializers.BooleanField()
    count = serializers.IntegerField()
    results = ComparedListingSerializer(many=True)
    cheapest_listing_id = serializers.IntegerField(required=False)
    nearest_listing_id = serializers.IntegerField(required=False)
    unavailable_listing_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class DiscoveredFarmerSerializer(serializers.Serializer):
    farmer_id = serializers.IntegerField()
    display_name = serializers.CharField()
    farm_name = serializers.CharField(allow_null=True)
    is_verified = serializers.BooleanField()
    main_produce = serializers.ListField(child=serializers.CharField())
    listed_produce = serializers.ListField(child=serializers.CharField())
    active_listings_count = serializers.IntegerField()
    location = PublicLocationSerializer(allow_null=True)
