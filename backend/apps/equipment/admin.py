from django.contrib import admin

from .models import EquipmentBooking, EquipmentListing


@admin.register(EquipmentListing)
class EquipmentListingAdmin(admin.ModelAdmin):
    list_display = ["name", "type", "owner", "rate", "rate_unit", "capacity", "is_available"]
    list_filter = ["type", "is_available"]
    raw_id_fields = ["owner"]


@admin.register(EquipmentBooking)
class EquipmentBookingAdmin(admin.ModelAdmin):
    list_display = ["listing", "requester", "start", "end", "status", "estimated_cost"]
    list_filter = ["status"]
    raw_id_fields = ["listing", "requester"]
