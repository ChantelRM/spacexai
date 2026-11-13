from django.conf import settings
from django.db import models


class RecommendationLog(models.Model):
    """One row per recommendation run: who asked, with what, and what came back."""

    class Direction(models.TextChoices):
        BUYER_TO_FARMER = "BUYER_TO_FARMER", "Buyer → farmers"
        FARMER_TO_BUYER = "FARMER_TO_BUYER", "Farmer → buyers"

    class Source(models.TextChoices):
        DASHBOARD = "dashboard", "Dashboard"
        AI = "ai", "AI assistant"
        API = "api", "API"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recommendation_logs")
    direction = models.CharField(max_length=16, choices=Direction.choices)
    source = models.CharField(max_length=10, choices=Source.choices)
    criteria = models.JSONField(default=dict)
    results = models.JSONField(default=list, help_text="[{id, score}] in ranked order")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
