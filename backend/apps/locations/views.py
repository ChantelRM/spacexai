from django.db import IntegrityError, transaction
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import UserLocation
from .serializers import MyLocationSerializer


class MyLocationView(APIView):
    """
    The current user's own location (including exact coordinates).

    - GET: 404 ``not_found`` until a location has been saved.
    - PUT: create or replace.
    - PATCH: partial update of an existing location.
    """

    permission_classes = [IsAuthenticated]

    def _get(self, request):
        try:
            return request.user.location
        except UserLocation.DoesNotExist:
            raise NotFound("You have not set your location yet.")

    @extend_schema(responses=MyLocationSerializer)
    def get(self, request):
        return Response(MyLocationSerializer(self._get(request)).data)

    @extend_schema(request=MyLocationSerializer, responses={200: MyLocationSerializer, 201: MyLocationSerializer})
    def put(self, request):
        instance = UserLocation.objects.filter(user=request.user).first()
        serializer = MyLocationSerializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                location = serializer.save(user=request.user)
        except IntegrityError:
            raise ValidationError("Your location could not be saved. Please try again.")
        return Response(
            MyLocationSerializer(location).data,
            status=status.HTTP_200_OK if instance else status.HTTP_201_CREATED,
        )

    @extend_schema(request=MyLocationSerializer, responses=MyLocationSerializer)
    def patch(self, request):
        serializer = MyLocationSerializer(self._get(request), data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        return Response(MyLocationSerializer(serializer.save()).data)
