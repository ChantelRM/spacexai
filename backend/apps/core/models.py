from django.db import models


class TimeStampedModel(models.Model):
    """Abstract base model: every table gets created_at / updated_at."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Notification(models.Model):
    """In-app notification. The mobile app polls /api/v1/notifications/ (no push in the MVP)."""

    user = models.ForeignKey("accounts.User", on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=40, db_index=True, help_text="e.g. order_accepted, new_message")
    message = models.CharField(max_length=300)
    link = models.CharField(max_length=200, blank=True, help_text="App route, e.g. orders/42")
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.type} -> {self.user_id}"
