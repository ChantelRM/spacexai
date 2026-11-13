from django.contrib import admin

from .models import RecommendationLog


@admin.register(RecommendationLog)
class RecommendationLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "direction", "source"]
    list_filter = ["direction", "source"]
    raw_id_fields = ["user"]
    readonly_fields = ["user", "direction", "source", "criteria", "results", "created_at"]
