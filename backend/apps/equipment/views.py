from decimal import Decimal

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination
from apps.core.permissions import IsFarmer
from apps.locations.models import UserLocation
from apps.locations.serializers import public_location

from . import services
from .models import EquipmentBooking, EquipmentListing

FARMER_ONLY = [IsAuthenticated, IsFarmer]


class EquipmentSerializer(serializers.ModelSerializer):
    owner = serializers.CharField(source="owner.display_name", read_only=True)
    location = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentListing
        fields = ["id", "owner", "type", "name", "description", "rate", "rate_unit", "capacity", "is_available",
                  "location", "created_at"]
        read_only_fields = ["id", "created_at"]
        extra_kwargs = {"rate": {"min_value": Decimal("0")}, "capacity": {"min_value": Decimal("0")}}

    def get_location(self, obj) -> dict | None:
        viewer = self.context["request"].user if "request" in self.context else None
        return public_location(UserLocation.objects.filter(user_id=obj.owner_id).first(),
                               UserLocation.objects.filter(user=viewer).first() if viewer else None)

    def validate(self, attrs):
        etype = attrs.get("type", getattr(self.instance, "type", None))
        capacity = attrs.get("capacity", getattr(self.instance, "capacity", None))
        if etype in ("COLD_STORAGE", "WAREHOUSE") and not capacity:
            raise serializers.ValidationError({"capacity": ["Storage needs a capacity in tonnes."]})
        return attrs


class BookingSerializer(serializers.ModelSerializer):
    equipment_id = serializers.IntegerField(source="listing_id", read_only=True)
    equipment_name = serializers.CharField(source="listing.name", read_only=True)
    requester = serializers.CharField(source="requester.display_name", read_only=True)

    class Meta:
        model = EquipmentBooking
        fields = ["id", "equipment_id", "equipment_name", "requester", "start", "end", "quantity", "status",
                  "estimated_cost", "notes", "created_at"]
        read_only_fields = fields


class BookingRequestSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False,
                                        help_text="Tonnes, for storage only")
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class EquipmentViewSet(viewsets.ModelViewSet):
    """Equipment and storage. List shows available items from others (``?mine=true`` for yours)."""

    permission_classes = FARMER_ONLY
    serializer_class = EquipmentSerializer
    queryset = EquipmentListing.objects.none()
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        p = self.request.query_params
        if self.action in ("update", "partial_update", "destroy") or p.get("mine") in ("true", "1"):
            qs = EquipmentListing.objects.filter(owner=self.request.user)
        else:
            qs = EquipmentListing.objects.filter(Q(is_available=True) | Q(owner=self.request.user))
        if p.get("type"):
            qs = qs.filter(type=p["type"].upper())
        return qs.select_related("owner")

    @extend_schema(parameters=[OpenApiParameter("type", str), OpenApiParameter("mine", bool)])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(request=BookingRequestSerializer, responses={201: BookingSerializer})
    @action(detail=True, methods=["post"])
    def book(self, request, pk=None):
        """Request a booking. The owner approves or declines; approved equipment bookings never overlap."""
        s = BookingRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        booking = services.request_booking(request.user, equipment_id=pk, **s.validated_data)
        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)


class BookingListView(APIView):
    """Bookings you requested (``?role=requester``, default) or received for your equipment (``?role=owner``)."""

    permission_classes = FARMER_ONLY

    @extend_schema(parameters=[OpenApiParameter("role", str, enum=["requester", "owner"])],
                   responses=BookingSerializer(many=True))
    def get(self, request):
        if request.query_params.get("role") == "owner":
            qs = EquipmentBooking.objects.filter(listing__owner=request.user)
        else:
            qs = EquipmentBooking.objects.filter(requester=request.user)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.select_related("listing", "requester").order_by("-start"), request, self)
        return paginator.get_paginated_response(BookingSerializer(page, many=True).data)


DecisionSerializer = inline_serializer("BookingDecision", {"approve": serializers.BooleanField()})


class BookingDecisionView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=DecisionSerializer, responses=BookingSerializer)
    def post(self, request, pk):
        approve = request.data.get("approve")
        if not isinstance(approve, bool):
            raise serializers.ValidationError({"approve": ["Must be true or false."]})
        return Response(BookingSerializer(services.decide(request.user, pk, approve)).data)


class BookingCancelView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=BookingSerializer)
    def post(self, request, pk):
        return Response(BookingSerializer(services.cancel(request.user, pk)).data)


class BookingCompleteView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=BookingSerializer)
    def post(self, request, pk):
        return Response(BookingSerializer(services.complete(request.user, pk)).data)
