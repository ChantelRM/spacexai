from rest_framework import serializers

from apps.locations.serializers import PublicLocationSerializer

from .models import FarmerProfile


class MyFarmerProfileSerializer(serializers.ModelSerializer):
    main_produce = serializers.ListField(child=serializers.CharField(max_length=80), max_length=30, required=False)

    class Meta:
        model = FarmerProfile
        fields = ["farm_name", "bio", "farm_size_hectares", "main_produce", "is_verified", "created_at", "updated_at"]
        read_only_fields = ["is_verified", "created_at", "updated_at"]

    def validate_main_produce(self, value):
        cleaned = []
        for item in value:
            item = " ".join(item.split())
            if item and item.lower() not in {c.lower() for c in cleaned}:
                cleaned.append(item)
        return cleaned


class PublicFarmerSerializer(serializers.Serializer):
    """Schema for services.public_farmer_profile()."""

    farmer_id = serializers.IntegerField()
    display_name = serializers.CharField()
    farm_name = serializers.CharField(allow_null=True)
    bio = serializers.CharField(allow_blank=True)
    farm_size_hectares = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    main_produce = serializers.ListField(child=serializers.CharField())
    is_verified = serializers.BooleanField()
    location = PublicLocationSerializer(allow_null=True)
    active_listings_count = serializers.IntegerField()
    completed_orders_count = serializers.IntegerField()
