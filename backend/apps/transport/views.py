from decimal import Decimal

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination
from apps.core.permissions import IsFarmer

from . import services
from .models import SplitMethod, TransportParticipant, TransportRequest, TransportStatus

FARMER_ONLY = [IsAuthenticated, IsFarmer]


class LoadSerializer(serializers.Serializer):
    load_weight_kg = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False)
    load_volume_m3 = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False)
    load_space_units = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"),
                                                required=False)
    pickup_town = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    agreed_amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False)


class ParticipantSerializer(serializers.ModelSerializer):
    farmer_id = serializers.IntegerField(read_only=True)
    display_name = serializers.CharField(source="farmer.display_name", read_only=True)

    class Meta:
        model = TransportParticipant
        fields = ["farmer_id", "display_name", "load_weight_kg", "load_volume_m3", "load_space_units", "pickup_town",
                  "agreed_amount", "calculated_share", "confirmed"]


class TransportRequestSerializer(serializers.ModelSerializer):
    organiser = serializers.CharField(source="organiser.display_name", read_only=True)
    participants = ParticipantSerializer(many=True, read_only=True)
    split_problem = serializers.SerializerMethodField()
    organiser_load = LoadSerializer(write_only=True, required=False, help_text="Add your own load straight away.")

    class Meta:
        model = TransportRequest
        fields = ["id", "organiser", "pickup_province", "pickup_municipality", "pickup_town", "destination",
                  "destination_town", "destination_municipality", "destination_province", "destination_latitude",
                  "destination_longitude", "travel_date", "vehicle_description", "total_cost", "capacity",
                  "capacity_unit", "cost_split_method", "notes", "status", "participants", "split_problem",
                  "organiser_load", "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def get_split_problem(self, obj) -> str | None:
        return services.compute_shares(obj)["problem"]

    def validate(self, attrs):
        lat, lng = attrs.get("destination_latitude"), attrs.get("destination_longitude")
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({"destination_latitude": ["Give both coordinates or neither."]})
        return attrs


CostSerializer = inline_serializer("TransportCost", {
    "total_cost": serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"), required=False),
    "cost_split_method": serializers.ChoiceField(SplitMethod.values, required=False)})
StatusSerializer = inline_serializer("TransportStatusChange", {
    "status": serializers.ChoiceField([TransportStatus.CONFIRMED, TransportStatus.COMPLETED,
                                       TransportStatus.CANCELLED])})


def _detail(pk):
    return Response(TransportRequestSerializer(services.get_request(pk)).data)


class TransportListView(APIView):
    """Shared trips. ``?mine=true`` for trips you organise or joined. POST to organise one."""

    permission_classes = FARMER_ONLY

    @extend_schema(parameters=[OpenApiParameter("status", str), OpenApiParameter("mine", bool)],
                   responses=TransportRequestSerializer(many=True))
    def get(self, request):
        qs = TransportRequest.objects.select_related("organiser").prefetch_related("participants__farmer")
        p = request.query_params
        if p.get("mine") in ("true", "1"):
            from django.db.models import Q

            qs = qs.filter(Q(organiser=request.user) | Q(participants__farmer=request.user)).distinct()
        if p.get("status"):
            qs = qs.filter(status=p["status"].upper())
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("travel_date", "-id"), request, self)
        return paginator.get_paginated_response(TransportRequestSerializer(page, many=True).data)

    @extend_schema(request=TransportRequestSerializer, responses={201: TransportRequestSerializer})
    def post(self, request):
        s = TransportRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        load = data.pop("organiser_load", None)
        tr = services.create_request(request.user, organiser_load=dict(load) if load else None, **data)
        return Response(TransportRequestSerializer(tr).data, status=status.HTTP_201_CREATED)


class TransportDetailView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(responses=TransportRequestSerializer)
    def get(self, request, pk):
        return _detail(pk)


class JoinView(APIView):
    """Join with your load (required field depends on the split method). Recalculates everyone's share."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=LoadSerializer, responses=TransportRequestSerializer)
    def post(self, request, pk):
        s = LoadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        services.join(request.user, pk, **s.validated_data)
        return _detail(pk)


class LeaveView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=TransportRequestSerializer)
    def post(self, request, pk):
        services.leave(request.user, pk)
        return _detail(pk)


class CostView(APIView):
    """Organiser sets the quoted total and/or split method."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=CostSerializer, responses=TransportRequestSerializer)
    def post(self, request, pk):
        total = request.data.get("total_cost")
        method = request.data.get("cost_split_method")
        if method and method not in SplitMethod.values:
            raise serializers.ValidationError({"cost_split_method": ["Unknown split method."]})
        try:
            total = Decimal(str(total)) if total not in (None, "") else None
        except Exception:
            raise serializers.ValidationError({"total_cost": ["Enter an amount."]})
        if total is not None and total < 0:
            raise serializers.ValidationError({"total_cost": ["Can't be negative."]})
        services.update_cost(request.user, pk, total_cost=total, cost_split_method=method)
        return _detail(pk)


class ConfirmView(APIView):
    """Confirm your share: a commitment to pay it (settled outside the app)."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=TransportRequestSerializer)
    def post(self, request, pk):
        services.confirm(request.user, pk)
        return _detail(pk)


class StatusView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=StatusSerializer, responses=TransportRequestSerializer)
    def post(self, request, pk):
        target = (request.data.get("status") or "").upper()
        if target not in (TransportStatus.CONFIRMED, TransportStatus.COMPLETED, TransportStatus.CANCELLED):
            raise serializers.ValidationError({"status": ["Use CONFIRMED, COMPLETED or CANCELLED."]})
        services.set_status(request.user, pk, target)
        return _detail(pk)
