from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsFarmer, IsWholesaleBuyer

from . import services
from .serializers import (
    BuyerMatchListSerializer,
    MultiItemRecommendationSerializer,
    RecommendFarmersRequestSerializer,
)


class RecommendFarmersView(APIView):
    """Ranked farmers for ad hoc criteria, per item, with reasons and shortfalls (buyers only)."""

    permission_classes = [IsAuthenticated, IsWholesaleBuyer]

    @extend_schema(request=RecommendFarmersRequestSerializer, responses=MultiItemRecommendationSerializer)
    def post(self, request):
        s = RecommendFarmersRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = dict(s.validated_data)
        items = [dict(i) for i in data.pop("items")]
        limit = data.pop("limit")
        return Response(services.recommend_farmers_for_items(request.user, items, source="api", limit=limit,
                                                             **data))


class BuyerDashboardRecommendationsView(APIView):
    """Recommended farmers for each of your open requirements (dashboard)."""

    permission_classes = [IsAuthenticated, IsWholesaleBuyer]

    @extend_schema(responses=MultiItemRecommendationSerializer)
    def get(self, request):
        return Response(services.dashboard_farmers_for_buyer(request.user))


class FarmerDashboardRecommendationsView(APIView):
    """Open buyer requirements that match your listings (dashboard)."""

    permission_classes = [IsAuthenticated, IsFarmer]

    @extend_schema(parameters=[OpenApiParameter("produce", str), OpenApiParameter("listing_id", int),
                               OpenApiParameter("max_distance_km", int)],
                   responses=BuyerMatchListSerializer)
    def get(self, request):
        params = request.query_params
        max_km = params.get("max_distance_km")
        return Response(services.search_buyer_requirements(
            request.user, produce=params.get("produce") or None, listing_id=params.get("listing_id") or None,
            max_distance_km=int(max_km) if max_km and max_km.isdigit() else None, source="dashboard"))
