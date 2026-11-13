from decimal import Decimal

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.costs import money_strings
from apps.core.pagination import StandardPagination
from apps.core.permissions import IsFarmer
from apps.groups.models import FarmerGroup

from . import services
from .calculations import calculate_cost_shares, validate_tiers
from .models import BulkPurchase, BulkStatus

FARMER_ONLY = [IsAuthenticated, IsFarmer]


class TierSerializer(serializers.Serializer):
    min_total_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class BulkPurchaseSerializer(serializers.ModelSerializer):
    group = serializers.PrimaryKeyRelatedField(queryset=FarmerGroup.objects.all(), required=False, allow_null=True)
    discount_tiers = TierSerializer(many=True, required=False)
    organiser_quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"),
                                                  required=False, write_only=True,
                                                  help_text="Join straight away with this quantity.")
    organiser = serializers.CharField(source="organiser.display_name", read_only=True)
    breakdown = serializers.SerializerMethodField()

    class Meta:
        model = BulkPurchase
        fields = ["id", "organiser", "group", "item_name", "category", "description", "unit", "unit_price",
                  "discount_tiers", "shared_fees", "supplier_name", "supplier_contact", "deadline", "status",
                  "organiser_quantity", "breakdown", "created_at"]
        read_only_fields = ["id", "status", "created_at"]
        extra_kwargs = {"unit_price": {"min_value": Decimal("0")}, "shared_fees": {"min_value": Decimal("0")}}

    def validate_discount_tiers(self, value):
        try:
            return validate_tiers([dict(t) for t in value])
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

    def get_breakdown(self, obj) -> dict:
        return money_strings(services.breakdown(obj))


class QuantitySerializer(serializers.Serializer):
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))


StatusSerializer = inline_serializer("BulkStatusChange", {
    "status": serializers.ChoiceField([BulkStatus.LOCKED, BulkStatus.ORDERED, BulkStatus.COMPLETED,
                                       BulkStatus.CANCELLED])})


class BulkListView(APIView):
    """Bulk purchases you can see (open to all, your groups', yours). ``?status=OPEN&category=FERTILISER``."""

    permission_classes = FARMER_ONLY

    @extend_schema(parameters=[OpenApiParameter("status", str), OpenApiParameter("category", str),
                               OpenApiParameter("mine", bool)],
                   responses=BulkPurchaseSerializer(many=True))
    def get(self, request):
        qs = services.visible_purchases(request.user)
        p = request.query_params
        if p.get("status"):
            qs = qs.filter(status=p["status"].upper())
        if p.get("category"):
            qs = qs.filter(category=p["category"].upper())
        if p.get("mine") in ("true", "1"):
            qs = qs.filter(members__farmer=request.user).distinct()
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.select_related("organiser").order_by("deadline", "-id"), request, self)
        return paginator.get_paginated_response(BulkPurchaseSerializer(page, many=True).data)

    @extend_schema(request=BulkPurchaseSerializer, responses={201: BulkPurchaseSerializer})
    def post(self, request):
        s = BulkPurchaseSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        bp = services.create_purchase(request.user, **s.validated_data)
        return Response(BulkPurchaseSerializer(bp).data, status=status.HTTP_201_CREATED)


class BulkDetailView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(responses=BulkPurchaseSerializer)
    def get(self, request, pk):
        return Response(BulkPurchaseSerializer(services.get_purchase(request.user, pk)).data)

    @extend_schema(request=BulkPurchaseSerializer, responses=BulkPurchaseSerializer)
    def patch(self, request, pk):
        """Organiser updates price, tiers or fees while OPEN (everyone is recalculated)."""
        s = BulkPurchaseSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        allowed = {k: v for k, v in s.validated_data.items()
                   if k in ("unit_price", "discount_tiers", "shared_fees", "description", "deadline",
                            "supplier_name", "supplier_contact")}
        return Response(BulkPurchaseSerializer(services.update_terms(request.user, pk, **allowed)).data)


class JoinView(APIView):
    """Join (or change your quantity). Recalculates everyone; does NOT commit you to pay."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=QuantitySerializer, responses=BulkPurchaseSerializer)
    def post(self, request, pk):
        s = QuantitySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.join(request.user, pk, s.validated_data["quantity"])
        return Response(BulkPurchaseSerializer(services.get_purchase(request.user, pk)).data)


class LeaveView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses={204: None})
    def post(self, request, pk):
        services.leave(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConfirmView(APIView):
    """Confirm your calculated contribution: a commitment to pay the organiser outside the app."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=BulkPurchaseSerializer)
    def post(self, request, pk):
        services.confirm(request.user, pk)
        return Response(BulkPurchaseSerializer(services.get_purchase(request.user, pk)).data)


class StatusView(APIView):
    """Organiser: LOCKED (only when everyone confirmed), ORDERED, COMPLETED or CANCELLED."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=StatusSerializer, responses=BulkPurchaseSerializer)
    def post(self, request, pk):
        target = (request.data.get("status") or "").upper()
        if target not in (BulkStatus.LOCKED, BulkStatus.ORDERED, BulkStatus.COMPLETED, BulkStatus.CANCELLED):
            raise serializers.ValidationError({"status": ["Use LOCKED, ORDERED, COMPLETED or CANCELLED."]})
        return Response(BulkPurchaseSerializer(services.set_status(request.user, pk, target)).data)


class CalculatorSerializer(serializers.Serializer):
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    discount_tiers = TierSerializer(many=True, required=False)
    shared_fees = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), default=0)
    method = serializers.ChoiceField(["quantity", "equal"], default="quantity")
    lines = inline_serializer("CostLine", {"label": serializers.CharField(max_length=80),
                                           "quantity": serializers.DecimalField(max_digits=12, decimal_places=2,
                                                                                min_value=Decimal("0"))},
                              many=True, min_length=1, max_length=100)


class CalculatorView(APIView):
    """Try a split without saving anything (e.g. before creating a bulk purchase)."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=CalculatorSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request):
        s = CalculatorSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            tiers = validate_tiers([dict(t) for t in d.get("discount_tiers", [])])
            return Response(money_strings(calculate_cost_shares([dict(line) for line in d["lines"]], d["unit_price"],
                                                                tiers, d["shared_fees"], d["method"])))
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

