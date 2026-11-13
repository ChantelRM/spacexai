import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel


class AIConversation(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_conversations")
    title = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or str(self.id)


class AIMessage(models.Model):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"
        TOOL = "tool", "Tool"

    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField(blank=True)
    tool_name = models.CharField(max_length=64, blank=True)
    tool_call_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]

    def __str__(self):
        return f"{self.role}: {self.content[:60]}"


class AIActionLog(models.Model):
    """Append-only audit trail: one row per tool call or confirmation event."""

    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        DENIED = "denied", "Denied"
        INVALID = "invalid", "Invalid arguments"
        ERROR = "error", "Error"
        PENDING_CONFIRMATION = "pending_confirmation", "Pending confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_action_logs")
    conversation = models.ForeignKey(
        AIConversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_logs"
    )
    tool_name = models.CharField(max_length=64, db_index=True)
    arguments = models.JSONField(default=dict, blank=True)
    result_summary = models.TextField(blank=True)
    status = models.CharField(max_length=24, choices=Status.choices, db_index=True)
    requires_confirmation = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.tool_name} [{self.status}] by {self.user_id}"


def default_pending_expiry():
    return timezone.now() + timedelta(minutes=settings.AI_PENDING_ACTION_TTL_MINUTES)


class PendingAction(TimeStampedModel):
    """
    A consequential action proposed by the AI that only runs after the user
    explicitly confirms it through POST /api/v1/ai/actions/{id}/confirm/.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        EXECUTING = "executing", "Executing"
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_pending_actions")
    conversation = models.ForeignKey(
        AIConversation, on_delete=models.SET_NULL, null=True, blank=True, related_name="pending_actions"
    )
    tool_name = models.CharField(max_length=64)
    arguments = models.JSONField(default=dict)
    summary = models.TextField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    expires_at = models.DateTimeField(default=default_pending_expiry)
    executed_at = models.DateTimeField(null=True, blank=True)
    result = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.tool_name} [{self.status}]: {self.summary[:60]}"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at
