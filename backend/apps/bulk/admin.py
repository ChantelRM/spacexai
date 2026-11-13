from django.contrib import admin

from .models import BulkPurchase, BulkPurchaseMember


class MemberInline(admin.TabularInline):
    model = BulkPurchaseMember
    extra = 0
    raw_id_fields = ["farmer"]


@admin.register(BulkPurchase)
class BulkPurchaseAdmin(admin.ModelAdmin):
    list_display = ["item_name", "category", "organiser", "unit_price", "deadline", "status"]
    list_filter = ["status", "category"]
    search_fields = ["item_name", "supplier_name"]
    raw_id_fields = ["organiser", "group"]
    inlines = [MemberInline]
