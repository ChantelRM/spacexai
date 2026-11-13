from decimal import Decimal

from rest_framework import serializers

from .models import Order, OrderItem, OrderStatusHistory, PaymentStatus


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "listing", "produce_name", "unit", "price_per_unit", "quantity", "line_total"]


class OrderHistorySerializer(serializers.ModelSerializer):
    changed_by = serializers.CharField(source="changed_by.display_name", default=None)

    class Meta:
        model = OrderStatusHistory
        fields = ["from_status", "to_status", "changed_by", "note", "created_at"]


class PartySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    display_name = serializers.CharField()


class OrderSerializer(serializers.ModelSerializer):
    buyer = PartySerializer(read_only=True)
    farmer = PartySerializer(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    history = OrderHistorySerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "buyer", "farmer", "status", "payment_status", "delivery_date", "delivery_notes", "total_amount",
            "rejection_reason", "cancellation_reason", "buyer_requirement", "items", "history",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class OrderLineInputSerializer(serializers.Serializer):
    listing_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                        help_text="In the listing's unit.")


class OrderCreateSerializer(serializers.Serializer):
    items = OrderLineInputSerializer(many=True, min_length=1, max_length=20)
    delivery_date = serializers.DateField(required=False, allow_null=True)
    delivery_notes = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")
    buyer_requirement_id = serializers.IntegerField(required=False, allow_null=True)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500, default="")


class PaymentStatusSerializer(serializers.Serializer):
    payment_status = serializers.ChoiceField(choices=PaymentStatus.values)
