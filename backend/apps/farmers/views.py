from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsFarmer

from . import services
from .models import FarmerProfile
from .serializers import MyFarmerProfileSerializer, PublicFarmerSerializer


class MyFarmerProfileView(APIView):
    """The current farmer's profile. GET is 404 until it has been saved with PUT."""

    permission_classes = [IsFarmer]

    def _get(self, request):
        profile = FarmerProfile.objects.filter(user=request.user).first()
        if profile is None:
            raise NotFound("You have not set up your farm profile yet.")
        return profile

    @extend_schema(responses=MyFarmerProfileSerializer)
    def get(self, request):
        return Response(MyFarmerProfileSerializer(self._get(request)).data)

    @extend_schema(request=MyFarmerProfileSerializer,
                   responses={200: MyFarmerProfileSerializer, 201: MyFarmerProfileSerializer})
    def put(self, request):
        instance = FarmerProfile.objects.filter(user=request.user).first()
        serializer = MyFarmerProfileSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = serializer.save(user=request.user)
        return Response(MyFarmerProfileSerializer(profile).data,
                        status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED)

    @extend_schema(request=MyFarmerProfileSerializer, responses=MyFarmerProfileSerializer)
    def patch(self, request):
        serializer = MyFarmerProfileSerializer(self._get(request), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(MyFarmerProfileSerializer(serializer.save()).data)


class PublicFarmerView(APIView):
    """Public farmer profile: farm details, area, approximate distance from you, counts. No contact details."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=PublicFarmerSerializer)
    def get(self, request, pk):
        return Response(PublicFarmerSerializer(services.public_farmer_profile(request.user, pk)).data)
