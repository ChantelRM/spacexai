from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.listings.models import ProduceCategory
from apps.locations.serializers import PublicLocationSerializer

from .models import BuyerRequirement, WholesaleBuyerProfile


class MyBuyerProfileSerializer(serializers.ModelSerializer):
    produce_interests = serializers.ListField(child=serializers.CharField(max_length=80), max_length=30,
                                              required=False)

    class Meta:
        model = WholesaleBuyerProfile
        fields = ["business_name", "business_type", "description", "produce_interests", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class PublicBuyerSerializer(serializers.Serializer):
    buyer_id = serializers.IntegerField()
    display_name = serializers.CharField()
    business_name = serializers.CharField(allow_null=True)
    business_type = serializers.CharField(allow_null=True)
    description = serializers.CharField(allow_blank=True)
    location = PublicLocationSerializer(allow_null=True)
    open_requirements_count = serializers.IntegerField()


class RequirementSerializer(serializers.ModelSerializer):
    category = serializers.SlugRelatedField(slug_field="slug", queryset=ProduceCategory.objects.all(),
                                            required=False, allow_null=True)

    class Meta:
        model = BuyerRequirement
        fields = [
            "id", "produce_name", "produce_key", "category", "quantity_needed", "unit", "max_price_per_unit",
            "min_quality_grade", "needed_by", "max_distance_km", "recurring", "notes", "status",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "produce_key", "created_at", "updated_at"]
        extra_kwargs = {"quantity_needed": {"min_value": Decimal("0.01")},
                        "max_price_per_unit": {"min_value": Decimal("0")}}

    def validate_produce_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Enter the produce name.")
        return value

    def validate_needed_by(self, value):
        if self.instance is None and value < timezone.localdate():
            raise serializers.ValidationError("The needed-by date can't be in the past.")
        return value
