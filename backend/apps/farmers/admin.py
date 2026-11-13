from django.contrib import admin

from .models import FarmerProfile


@admin.register(FarmerProfile)
class FarmerProfileAdmin(admin.ModelAdmin):
    list_display = ["farm_name", "user", "is_verified", "created_at"]
    list_filter = ["is_verified"]
    list_editable = ["is_verified"]
    search_fields = ["farm_name", "user__email", "user__display_name"]
    raw_id_fields = ["user"]
