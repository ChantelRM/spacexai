from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role, User
from apps.core.permissions import IsWholesaleBuyer
from apps.locations.models import UserLocation
from apps.locations.serializers import public_location

from .models import BuyerRequirement, RequirementStatus, WholesaleBuyerProfile
from .serializers import MyBuyerProfileSerializer, PublicBuyerSerializer, RequirementSerializer


class MyBuyerProfileView(APIView):
    """The current buyer's business profile. GET is 404 until saved with PUT."""

    permission_classes = [IsAuthenticated, IsWholesaleBuyer]

    def _get(self, request):
        profile = WholesaleBuyerProfile.objects.filter(user=request.user).first()
        if profile is None:
            raise NotFound("You have not set up your business profile yet.")
        return profile

    @extend_schema(responses=MyBuyerProfileSerializer)
    def get(self, request):
        return Response(MyBuyerProfileSerializer(self._get(request)).data)

    @extend_schema(request=MyBuyerProfileSerializer,
                   responses={200: MyBuyerProfileSerializer, 201: MyBuyerProfileSerializer})
    def put(self, request):
        instance = WholesaleBuyerProfile.objects.filter(user=request.user).first()
        s = MyBuyerProfileSerializer(instance, data=request.data)
        s.is_valid(raise_exception=True)
        profile = s.save(user=request.user)
        return Response(MyBuyerProfileSerializer(profile).data,
                        status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)

    @extend_schema(request=MyBuyerProfileSerializer, responses=MyBuyerProfileSerializer)
    def patch(self, request):
        s = MyBuyerProfileSerializer(self._get(request), data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        return Response(MyBuyerProfileSerializer(s.save()).data)


class PublicBuyerView(APIView):
    """Public buyer profile: business details, area and approximate distance. No contact details."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PublicBuyerSerializer)
    def get(self, request, pk):
        buyer = User.objects.filter(pk=pk, role=Role.WHOLESALE_BUYER, is_active=True).first()
        if buyer is None:
            raise NotFound("Buyer not found.")
        profile = WholesaleBuyerProfile.objects.filter(user=buyer).first()
        data = {
            "buyer_id": buyer.pk,
            "display_name": buyer.display_name,
            "business_name": profile.business_name if profile else None,
            "business_type": profile.business_type if profile else None,
            "description": profile.description if profile else "",
            "location": public_location(UserLocation.objects.filter(user=buyer).first(),
                                        UserLocation.objects.filter(user=request.user).first()),
            "open_requirements_count": BuyerRequirement.objects.filter(buyer=buyer,
                                                                       status=RequirementStatus.OPEN).count(),
        }
        return Response(PublicBuyerSerializer(data).data)


class RequirementViewSet(viewsets.ModelViewSet):
    """Your produce requirements. ``?status=OPEN|FULFILLED|CLOSED``. DELETE closes the requirement."""

    permission_classes = [IsAuthenticated, IsWholesaleBuyer]
    serializer_class = RequirementSerializer
    queryset = BuyerRequirement.objects.none()  # schema only; scoped in get_queryset
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_queryset(self):
        qs = BuyerRequirement.objects.filter(buyer=self.request.user).select_related("category")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"].upper())
        return qs

    def perform_create(self, serializer):
        serializer.save(buyer=self.request.user)

    def perform_destroy(self, instance):
        instance.status = RequirementStatus.CLOSED
        instance.save(update_fields=["status", "updated_at"])
