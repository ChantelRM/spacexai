from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.permissions import IsWholesaleBuyer

from . import services
from .models import Order
from .serializers import OrderCreateSerializer, OrderSerializer, PaymentStatusSerializer, ReasonSerializer


class OrderViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Buyers see the orders they placed; farmers see orders addressed to them.
    Status changes go through the action endpoints (the state machine).
    """

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer
    queryset = Order.objects.none()  # for schema generation; real queryset is role-scoped below

    def get_queryset(self):
        qs = services.visible_orders(self.request.user).select_related("buyer", "farmer").prefetch_related(
            "items", "history__changed_by")
        if self.request.query_params.get("status"):
            qs = qs.filter(status__in=self.request.query_params["status"].upper().split(","))
        return qs

    @extend_schema(parameters=[OpenApiParameter("status", str, description="Comma-separated statuses")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=OrderCreateSerializer, responses={201: OrderSerializer})
    def create(self, request):
        if not IsWholesaleBuyer().has_permission(request, self):
            raise PermissionDenied("Only wholesale buyers can place orders.")
        s = OrderCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        order = services.create_order(request.user, items=[dict(i) for i in data["items"]],
                                      delivery_date=data.get("delivery_date"),
                                      delivery_notes=data.get("delivery_notes", ""),
                                      buyer_requirement_id=data.get("buyer_requirement_id"))
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    def _transition(self, request, pk, name):
        s = ReasonSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        order = services.transition(request.user, pk, name, reason=s.validated_data["reason"])
        return Response(OrderSerializer(order).data)

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        """Farmer accepts: stock is reserved. Fails if stock is insufficient."""
        return self._transition(request, pk, "accept")

    @extend_schema(request=ReasonSerializer, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        """Farmer rejects a pending order (reason required)."""
        return self._transition(request, pk, "reject")

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"], url_path="dispatch")
    def mark_dispatched(self, request, pk=None):
        """Farmer marks an accepted order as dispatched."""
        return self._transition(request, pk, "dispatch")

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"], url_path="confirm-receipt")
    def confirm_receipt(self, request, pk=None):
        """Buyer confirms the delivery arrived."""
        return self._transition(request, pk, "confirm_receipt")

    @extend_schema(request=None, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self._transition(request, pk, "complete")

    @extend_schema(request=ReasonSerializer, responses=OrderSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        """Buyer cancels a pending order; either party cancels an accepted order (reason required)."""
        return self._transition(request, pk, "cancel")

    @extend_schema(request=PaymentStatusSerializer, responses=OrderSerializer)
    @action(detail=True, methods=["post"], url_path="payment-status")
    def payment_status(self, request, pk=None):
        """Payment is settled outside the app. Farmer marks PAID/UNPAID; either party may flag DISPUTED."""
        s = PaymentStatusSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(OrderSerializer(services.set_payment_status(request.user, pk,
                                                                    s.validated_data["payment_status"])).data)
