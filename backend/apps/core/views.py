from django.db import connection
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Notification
from .serializers import NotificationSerializer, UnreadCountSerializer


class HealthCheckView(APIView):
    """Liveness/readiness probe. Public and unthrottled."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(
        auth=[],
        responses=inline_serializer(
            "HealthCheck",
            {"status": serializers.CharField(), "database": serializers.CharField()},
        ),
    )
    def get(self, request):
        db_status = "ok"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            db_status = "unavailable"
        return Response({"status": "ok" if db_status == "ok" else "degraded", "database": db_status})



class NotificationListView(generics.ListAPIView):
    """Your notifications, newest first. ``?unread=true`` for unread only."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    @extend_schema(parameters=[OpenApiParameter("unread", bool, required=False)])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") in ("true", "1"):
            qs = qs.filter(is_read=False)
        return qs


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UnreadCountSerializer)
    def get(self, request):
        return Response({"unread": Notification.objects.filter(user=request.user, is_read=False).count()})


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=NotificationSerializer)
    def post(self, request, pk):
        notification = Notification.objects.filter(pk=pk, user=request.user).first()
        if notification is None:
            raise NotFound("Notification not found.")
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=UnreadCountSerializer)
    def post(self, request):
        Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
        return Response({"unread": 0})
