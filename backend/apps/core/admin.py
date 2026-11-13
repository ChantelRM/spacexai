from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "type", "message", "is_read"]
    list_filter = ["type", "is_read"]
    raw_id_fields = ["user"]
