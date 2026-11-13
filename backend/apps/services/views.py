from decimal import Decimal

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination
from apps.core.permissions import IsFarmer
from apps.groups.models import FarmerGroup
from apps.locations.models import Province

from . import services
from .models import (
    INSURANCE_DISCLAIMER,
    AlertType,
    InsuranceProduct,
    InsuranceQuoteRequest,
    ServiceContribution,
    ServiceSplit,
    SharedServiceRequest,
)

FARMER_ONLY = [IsAuthenticated, IsFarmer]


# --- Shared security ------------------------------------------------------------------------

class ContributionSerializer(serializers.ModelSerializer):
    farmer_id = serializers.IntegerField(read_only=True)
    display_name = serializers.CharField(source="farmer.display_name", read_only=True)

    class Meta:
        model = ServiceContribution
        fields = ["farmer_id", "display_name", "agreed_amount", "amount", "confirmed"]


class SharedServiceSerializer(serializers.ModelSerializer):
    organiser = serializers.CharField(source="organiser.display_name", read_only=True)
    group = serializers.PrimaryKeyRelatedField(queryset=FarmerGroup.objects.all(), required=False, allow_null=True)
    contributions = ContributionSerializer(many=True, read_only=True)
    split_problem = serializers.SerializerMethodField()

    class Meta:
        model = SharedServiceRequest
        fields = ["id", "organiser", "service_type", "title", "description", "province", "municipality", "town",
                  "group", "total_monthly_cost", "split_method", "status", "contributions", "split_problem",
                  "created_at"]
        read_only_fields = ["id", "status", "created_at"]

    def get_split_problem(self, obj) -> str | None:
        return services.compute_contributions(obj)["problem"]


AmountSerializer = inline_serializer("AgreedAmount", {
    "agreed_amount": serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"),
                                              required=False, allow_null=True)})
ServiceCostSerializer = inline_serializer("ServiceCost", {
    "total_monthly_cost": serializers.DecimalField(max_digits=12, decimal_places=2, required=False),
    "split_method": serializers.ChoiceField(ServiceSplit.values, required=False)})


def _decimal_or_none(value, field):
    if value in (None, ""):
        return None
    try:
        value = Decimal(str(value))
    except Exception:
        raise serializers.ValidationError({field: ["Enter an amount."]})
    if value < 0:
        raise serializers.ValidationError({field: ["Can't be negative."]})
    return value


def _service(pk):
    return Response(SharedServiceSerializer(services.get_service(pk)).data)


class SharedServiceListView(APIView):
    """Shared security arrangements (and other shared services). POST to organise one."""

    permission_classes = FARMER_ONLY

    @extend_schema(responses=SharedServiceSerializer(many=True))
    def get(self, request):
        from django.db.models import Q

        qs = SharedServiceRequest.objects.filter(
            Q(group__isnull=True) | Q(group__memberships__farmer=request.user, group__memberships__status="ACTIVE")
        ).distinct().select_related("organiser").prefetch_related("contributions__farmer")
        if request.query_params.get("municipality"):
            qs = qs.filter(municipality__iexact=request.query_params["municipality"])
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs.order_by("-created_at"), request, self)
        return paginator.get_paginated_response(SharedServiceSerializer(page, many=True).data)

    @extend_schema(request=SharedServiceSerializer, responses={201: SharedServiceSerializer})
    def post(self, request):
        s = SharedServiceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        service = services.create_service(request.user, **s.validated_data)
        return Response(SharedServiceSerializer(service).data, status=status.HTTP_201_CREATED)


class SharedServiceDetailView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(responses=SharedServiceSerializer)
    def get(self, request, pk):
        return _service(pk)


class SharedServiceJoinView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=AmountSerializer, responses=SharedServiceSerializer)
    def post(self, request, pk):
        services.join(request.user, pk, _decimal_or_none(request.data.get("agreed_amount"), "agreed_amount"))
        return _service(pk)


class SharedServiceLeaveView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=SharedServiceSerializer)
    def post(self, request, pk):
        services.leave(request.user, pk)
        return _service(pk)


class SharedServiceCostView(APIView):
    permission_classes = FARMER_ONLY

    @extend_schema(request=ServiceCostSerializer, responses=SharedServiceSerializer)
    def post(self, request, pk):
        method = request.data.get("split_method")
        if method and method not in ServiceSplit.values:
            raise serializers.ValidationError({"split_method": ["Use EQUAL or AGREED."]})
        services.update_cost(request.user, pk,
                             total_monthly_cost=_decimal_or_none(request.data.get("total_monthly_cost"),
                                                                 "total_monthly_cost"),
                             split_method=method)
        return _service(pk)


class SharedServiceConfirmView(APIView):
    """Confirm your monthly contribution (paid outside the app)."""

    permission_classes = FARMER_ONLY

    @extend_schema(request=None, responses=SharedServiceSerializer)
    def post(self, request, pk):
        services.confirm(request.user, pk)
        return _service(pk)


# --- Security alerts ---------------------------------------------------------------------------

class SecurityAlertSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    author_display_name = serializers.CharField(source="author.display_name", read_only=True)
    alert_type = serializers.ChoiceField(choices=AlertType.choices)
    title = serializers.CharField(max_length=120)
    body = serializers.CharField(max_length=2000)
    province = serializers.ChoiceField(choices=Province.choices)
    municipality = serializers.CharField(max_length=120)
    town = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    group = serializers.PrimaryKeyRelatedField(queryset=FarmerGroup.objects.all(), required=False, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)


class SecurityAlertListView(generics.ListAPIView):
    """Alerts for your municipality and your groups. Information only: no personal data about suspects."""

    permission_classes = FARMER_ONLY
    serializer_class = SecurityAlertSerializer

    def get_queryset(self):
        return services.visible_alerts(self.request.user)

    @extend_schema(request=SecurityAlertSerializer, responses={201: SecurityAlertSerializer})
    def post(self, request):
        s = SecurityAlertSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        alert = services.create_alert(request.user, **s.validated_data)
        return Response(SecurityAlertSerializer(alert).data, status=status.HTTP_201_CREATED)


# --- Insurance information -----------------------------------------------------------------------

class InsuranceProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = InsuranceProduct
        fields = ["id", "provider_name", "name", "category", "summary", "provider_contact", "website",
                  "is_authorised_provider"]


class QuoteRequestSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(queryset=InsuranceProduct.objects.filter(is_active=True),
                                                 required=False, allow_null=True)

    class Meta:
        model = InsuranceQuoteRequest
        fields = ["id", "product", "category", "details", "status", "quote_note", "quote_amount", "created_at"]
        read_only_fields = ["id", "status", "quote_note", "quote_amount", "created_at"]


def with_disclaimer(payload):
    return {"disclaimer": INSURANCE_DISCLAIMER, **payload}


class InsuranceProductListView(APIView):
    """Insurance information from admin-listed providers. Always includes the disclaimer."""

    permission_classes = FARMER_ONLY

    @extend_schema(responses=inline_serializer("InsuranceProducts", {
        "disclaimer": serializers.CharField(), "results": InsuranceProductSerializer(many=True)}))
    def get(self, request):
        qs = InsuranceProduct.objects.filter(is_active=True)
        if request.query_params.get("category"):
            qs = qs.filter(category=request.query_params["category"].upper())
        return Response(with_disclaimer({"results": InsuranceProductSerializer(qs, many=True).data}))


class QuoteRequestListView(APIView):
    """Your quote requests. An admin follows up with providers and records any quote."""

    permission_classes = FARMER_ONLY

    @extend_schema(responses=inline_serializer("QuoteRequests", {
        "disclaimer": serializers.CharField(), "results": QuoteRequestSerializer(many=True)}))
    def get(self, request):
        qs = InsuranceQuoteRequest.objects.filter(farmer=request.user)
        return Response(with_disclaimer({"results": QuoteRequestSerializer(qs, many=True).data}))

    @extend_schema(request=QuoteRequestSerializer, responses={201: inline_serializer("QuoteRequestCreated", {
        "disclaimer": serializers.CharField(), "quote_request": QuoteRequestSerializer()})})
    def post(self, request):
        s = QuoteRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data.get("product") and s.validated_data["product"].category != s.validated_data["category"]:
            raise serializers.ValidationError({"category": ["Doesn't match the product's category."]})
        quote = s.save(farmer=request.user)
        return Response(with_disclaimer({"quote_request": QuoteRequestSerializer(quote).data}),
                        status=status.HTTP_201_CREATED)
