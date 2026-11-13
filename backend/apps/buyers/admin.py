from django.contrib import admin

from .models import BuyerRequirement, WholesaleBuyerProfile


@admin.register(WholesaleBuyerProfile)
class WholesaleBuyerProfileAdmin(admin.ModelAdmin):
    list_display = ["business_name", "business_type", "user", "created_at"]
    list_filter = ["business_type"]
    search_fields = ["business_name", "user__email"]
    raw_id_fields = ["user"]


@admin.register(BuyerRequirement)
class BuyerRequirementAdmin(admin.ModelAdmin):
    list_display = ["produce_name", "buyer", "quantity_needed", "unit", "needed_by", "status"]
    list_filter = ["status", "unit", "recurring"]
    search_fields = ["produce_name", "buyer__email"]
    raw_id_fields = ["buyer"]
