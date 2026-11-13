from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import IsFarmer

from . import services
from .models import ListingImage, ProduceCategory, ProduceListing
from .serializers import (
    MAX_IMAGES_PER_LISTING,
    ImageUploadSerializer,
    ListingImageSerializer,
    MyListingSerializer,
    ProduceCategorySerializer,
)


class CategoryListView(ListAPIView):
    """Produce categories (for pickers)."""

    permission_classes = [IsAuthenticated]
    serializer_class = ProduceCategorySerializer
    queryset = ProduceCategory.objects.all()
    pagination_class = None


class MyListingViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, mixins.RetrieveModelMixin,
                       mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """
    The current farmer's own listings. Deleting is a soft delete (status DELETED).
    Filter with ``?status=ACTIVE|PAUSED|SOLD_OUT``.
    """

    permission_classes = [IsFarmer]
    serializer_class = MyListingSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_queryset(self):
        qs = (ProduceListing.objects.not_deleted().filter(farmer=self.request.user)
              .select_related("category").prefetch_related("images"))
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter.upper())
        return qs

    def perform_create(self, serializer):
        serializer.save(farmer=self.request.user)

    def perform_destroy(self, instance):
        services.soft_delete(self.request.user, instance.pk)

    @extend_schema(request=None, responses=MyListingSerializer)
    @action(detail=True, methods=["post"])
    def pause(self, request, pk=None):
        return Response(MyListingSerializer(services.set_paused(request.user, pk, True),
                                            context={"request": request}).data)

    @extend_schema(request=None, responses=MyListingSerializer)
    @action(detail=True, methods=["post"])
    def resume(self, request, pk=None):
        return Response(MyListingSerializer(services.set_paused(request.user, pk, False),
                                            context={"request": request}).data)

    @extend_schema(request={"multipart/form-data": ImageUploadSerializer},
                   responses={201: ListingImageSerializer})
    @action(detail=True, methods=["post"], url_path="images", parser_classes=[MultiPartParser, FormParser])
    def add_image(self, request, pk=None):
        serializer = ImageUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            listing = services.get_own_listing(request.user, pk, for_update=True)
            if listing.images.count() >= MAX_IMAGES_PER_LISTING:
                raise ValidationError({"image": [f"A listing can have at most {MAX_IMAGES_PER_LISTING} images."]})
            image = ListingImage.objects.create(listing=listing, image=serializer.validated_data["image"])
        return Response(ListingImageSerializer(image, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["delete"], url_path=r"images/(?P<image_id>\d+)")
    def delete_image(self, request, pk=None, image_id=None):
        listing = services.get_own_listing(request.user, pk)
        image = listing.images.filter(pk=image_id).first()
        if image is None:
            raise NotFound("Image not found.")
        image.image.delete(save=False)
        image.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
