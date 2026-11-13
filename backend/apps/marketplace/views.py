from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination

from . import services
from .serializers import CompareResponseSerializer, DiscoveredFarmerSerializer, PublicListingSerializer


def _paginated(request, view, rows, serializer_class):
    paginator = StandardPagination()
    page = paginator.paginate_queryset(rows, request, view=view)
    return paginator.get_paginated_response(serializer_class(page, many=True).data)


SEARCH_PARAMS = [
    OpenApiParameter("q", str, description="Produce name, e.g. tomatoes"),
    OpenApiParameter("category", str, description="Category slug"),
    OpenApiParameter("min_price", OpenApiTypes.DECIMAL), OpenApiParameter("max_price", OpenApiTypes.DECIMAL),
    OpenApiParameter("min_quantity", OpenApiTypes.DECIMAL, description="In `unit` (KG/TONNE convert)"),
    OpenApiParameter("unit", str), OpenApiParameter("quality_grade", str, description="Minimum quality"),
    OpenApiParameter("province", str), OpenApiParameter("municipality", str), OpenApiParameter("town", str),
    OpenApiParameter("max_distance_km", OpenApiTypes.DECIMAL,
                     description="From your location; GPS when both sides have it, otherwise area tiers"),
    OpenApiParameter("available_by", OpenApiTypes.DATE), OpenApiParameter("farmer_id", int),
    OpenApiParameter("sort", str, enum=sorted(services.SORTS)),
    OpenApiParameter("page", int), OpenApiParameter("page_size", int),
]


class ListingSearchView(APIView):
    """Search active listings with filters and sorting. Paginated."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=SEARCH_PARAMS, responses=PublicListingSerializer(many=True))
    def get(self, request):
        return _paginated(request, self, services.search_listings(request.user, request.query_params, request),
                          PublicListingSerializer)


class ListingDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PublicListingSerializer)
    def get(self, request, pk):
        return Response(PublicListingSerializer(services.listing_detail(request.user, pk, request)).data)


class CompareView(APIView):
    """Compare 2-5 listings side by side: ``?listing_ids=1,2,3``."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("listing_ids", str, required=True)],
                   responses=CompareResponseSerializer)
    def get(self, request):
        ids = [i for i in (request.query_params.get("listing_ids") or "").split(",") if i.strip()]
        return Response(CompareResponseSerializer(services.compare_listings(request.user, ids, request)).data)


class FarmerDiscoveryView(APIView):
    """Find farmers by area and produce, nearest first. Paginated."""

    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("produce", str), OpenApiParameter("province", str),
                               OpenApiParameter("municipality", str), OpenApiParameter("town", str),
                               OpenApiParameter("max_distance_km", OpenApiTypes.DECIMAL),
                               OpenApiParameter("verified", bool), OpenApiParameter("page", int),
                               OpenApiParameter("page_size", int)],
                   responses=DiscoveredFarmerSerializer(many=True))
    def get(self, request):
        return _paginated(request, self, services.discover_farmers(request.user, request.query_params),
                          DiscoveredFarmerSerializer)
