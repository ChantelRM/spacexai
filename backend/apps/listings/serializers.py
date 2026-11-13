from rest_framework import serializers

from .models import ListingImage, ProduceCategory, ProduceListing

MAX_IMAGES_PER_LISTING = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


class ProduceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProduceCategory
        fields = ["id", "name", "slug"]


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ["id", "image", "created_at"]
        read_only_fields = fields


class ImageUploadSerializer(serializers.Serializer):
    image = serializers.ImageField(help_text="JPEG, PNG or WebP, up to 5 MB.")

    def validate_image(self, image):
        if image.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError("Images must be 5 MB or smaller.")
        fmt = getattr(getattr(image, "image", None), "format", None)
        if fmt not in ALLOWED_IMAGE_FORMATS:
            raise serializers.ValidationError("Only JPEG, PNG and WebP images are allowed.")
        return image


class MyListingSerializer(serializers.ModelSerializer):
    """The owning farmer's view of a listing (create and edit)."""

    category = serializers.SlugRelatedField(slug_field="slug", queryset=ProduceCategory.objects.all(),
                                            required=False, allow_null=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default=None)
    images = ListingImageSerializer(many=True, read_only=True)

    class Meta:
        model = ProduceListing
        fields = [
            "id", "produce_name", "produce_key", "category", "category_name", "quantity_available", "unit",
            "price_per_unit", "quality_grade", "available_from", "available_until", "description",
            "status", "images", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "produce_key", "status", "images", "created_at", "updated_at"]
        extra_kwargs = {
            "quantity_available": {"min_value": 0},
            "price_per_unit": {"min_value": 0},
        }

    def validate_produce_name(self, value):
        value = " ".join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError("Enter the produce name.")
        return value

    def validate(self, attrs):
        start = attrs.get("available_from", getattr(self.instance, "available_from", None))
        end = attrs.get("available_until", getattr(self.instance, "available_until", None))
        if start and end and end < start:
            raise serializers.ValidationError({"available_until": ["Must be on or after available_from."]})
        return attrs
