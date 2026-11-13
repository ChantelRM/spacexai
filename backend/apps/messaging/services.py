from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Role, User
from apps.core.notifications import notify

from .models import Conversation, Message


def conversations_for(user):
    return Conversation.objects.filter(Q(buyer=user) | Q(farmer=user)).select_related("buyer", "farmer")


def get_conversation(user, conversation_id) -> Conversation:
    conv = conversations_for(user).filter(pk=conversation_id).first()
    if conv is None:
        raise NotFound("Conversation not found.")
    return conv


@transaction.atomic
def start_conversation(user, *, other_user_id, order_id=None, message="") -> Conversation:
    """Open (or reuse) the thread between a buyer and a farmer, optionally about an order."""
    other = User.objects.filter(pk=other_user_id, is_active=True).first()
    if other is None or other.pk == user.pk:
        raise ValidationError({"other_user_id": ["User not found."]})
    roles = {user.role, other.role}
    if roles != {Role.FARMER, Role.WHOLESALE_BUYER}:
        raise ValidationError({"other_user_id": ["Conversations are between a buyer and a farmer."]})
    buyer, farmer = (user, other) if user.role == Role.WHOLESALE_BUYER else (other, user)
    order = None
    if order_id:
        from apps.orders.models import Order

        order = Order.objects.filter(pk=order_id, buyer=buyer, farmer=farmer).first()
        if order is None:
            raise ValidationError({"order_id": ["Order not found for these participants."]})
    conv = Conversation.objects.filter(buyer=buyer, farmer=farmer, order=order).first()
    if conv is None:
        try:
            with transaction.atomic():
                conv = Conversation.objects.create(buyer=buyer, farmer=farmer, order=order)
        except IntegrityError:
            conv = Conversation.objects.get(buyer=buyer, farmer=farmer, order=order)
    if message.strip():
        send_message(user, conv.pk, message)
    return conv


@transaction.atomic
def send_message(user, conversation_id, body: str) -> Message:
    conv = get_conversation(user, conversation_id)
    body = (body or "").strip()
    if not body:
        raise ValidationError({"body": ["Message can't be empty."]})
    msg = Message.objects.create(conversation=conv, sender=user, body=body[:4000])
    conv.save(update_fields=["updated_at"])
    notify(conv.other_party(user), "new_message", f"New message from {user.display_name}.",
           f"messages/{conv.pk}")
    return msg


def mark_read(user, conversation_id) -> int:
    conv = get_conversation(user, conversation_id)
    return conv.messages.filter(read_at__isnull=True).exclude(sender=user).update(read_at=timezone.now())


def unread_count(user, conv) -> int:
    return conv.messages.filter(read_at__isnull=True).exclude(sender=user).count()
