"""Create in-app notifications. Call from services, never from views."""
from .models import Notification


def notify(user, type: str, message: str, link: str = "") -> Notification:
    return Notification.objects.create(user=user, type=type, message=message[:300], link=link[:200])
