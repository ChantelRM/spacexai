from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from rest_framework import serializers

from .distance import approximate_distance
from .models import Province, UserLocation

MAX_DELIVERY_AREAS = 30


class CoordinateField(serializers.DecimalField):
    """Accepts any precision from the phone's GPS and rounds to 6 dp (~11 cm)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_digits", 9)
        kwargs.setdefault("decimal_places", 6)
        kwargs.setdefault("coerce_to_string", False)
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        if data not in (None, ""):
            try:
                data = Decimal(str(data)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            except (InvalidOperation, ValueError):
                self.fail("invalid")
        return super().to_internal_value(data)


class DeliveryAreaSerializer(serializers.Serializer):
    province = serializers.ChoiceField(choices=Province.choices)
    municipality = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    town = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")


class MyLocationSerializer(serializers.ModelSerializer):
    """Owner view: includes exact coordinates. Only ever use for request.user."""

    latitude = CoordinateField(min_value=-90, max_value=90)
    longitude = CoordinateField(min_value=-180, max_value=180)
    preferred_delivery_areas = DeliveryAreaSerializer(many=True, required=False)
    province_display = serializers.CharField(source="get_province_display", read_only=True)

    class Meta:
        model = UserLocation
        fields = [
            "province", "province_display", "municipality", "town", "address_line",
            "latitude", "longitude", "share_precise_location", "preferred_delivery_areas",
            "created_at", "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def validate_preferred_delivery_areas(self, value):
        if len(value) > MAX_DELIVERY_AREAS:
            raise serializers.ValidationError(f"At most {MAX_DELIVERY_AREAS} delivery areas.")
        return [dict(item) for item in value]

    def validate(self, attrs):
        lat = attrs.get("latitude", getattr(self.instance, "latitude", None))
        lng = attrs.get("longitude", getattr(self.instance, "longitude", None))
        if (lat is None) != (lng is None):
            raise serializers.ValidationError(
                {"latitude": ["Latitude and longitude must both be set or both be empty."]}
            )
        for field in ("municipality", "town"):
            if field in attrs:
                attrs[field] = " ".join(attrs[field].split())
        return attrs


def public_location(location, viewer_location=None) -> dict | None:
    """
    What OTHER users may see about a location: area names and an approximate
    distance from the viewer. Never includes coordinates or address_line.
    Use this (not MyLocationSerializer) whenever showing someone else's location.
    """
    if location is None:
        return None
    return {
        "province": location.province,
        "province_display": location.get_province_display(),
        "municipality": location.municipality,
        "town": location.town,
        "distance": approximate_distance(viewer_location, location),
    }


class DistanceSerializer(serializers.Serializer):
    km = serializers.IntegerField(allow_null=True)
    basis = serializers.CharField()
    label = serializers.CharField()


class PublicLocationSerializer(serializers.Serializer):
    """Schema for ``public_location()`` output (for OpenAPI docs)."""

    province = serializers.CharField()
    province_display = serializers.CharField()
    municipality = serializers.CharField()
    town = serializers.CharField()
    distance = DistanceSerializer()
