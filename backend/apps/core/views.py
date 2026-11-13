from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


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
