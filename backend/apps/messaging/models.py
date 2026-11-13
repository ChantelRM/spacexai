from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Conversation(TimeStampedModel):
    """A thread between one buyer and one farmer, optionally about an order."""

    buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="buyer_conversations")
    farmer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="farmer_conversations")
    order = models.ForeignKey("orders.Order", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="conversations")

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["buyer", "farmer", "order"], name="unique_conversation_per_order"),
            models.UniqueConstraint(fields=["buyer", "farmer"], condition=models.Q(order__isnull=True),
                                    name="unique_general_conversation"),
        ]

    def is_participant(self, user) -> bool:
        return user.pk in (self.buyer_id, self.farmer_id)

    def other_party(self, user):
        return self.farmer if user.pk == self.buyer_id else self.buyer


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(max_length=4000)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]
