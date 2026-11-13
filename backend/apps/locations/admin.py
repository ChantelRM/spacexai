from django.contrib import admin

from .models import UserLocation


@admin.register(UserLocation)
class UserLocationAdmin(admin.ModelAdmin):
    list_display = ["user", "province", "municipality", "town", "has_coordinates", "updated_at"]
    list_filter = ["province", "share_precise_location"]
    search_fields = ["user__email", "user__display_name", "municipality", "town"]
    raw_id_fields = ["user"]

    @admin.display(boolean=True)
    def has_coordinates(self, obj):
        return obj.has_coordinates
