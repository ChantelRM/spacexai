from django.contrib import admin

from .models import Order, OrderItem, OrderStatusHistory


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ["listing"]


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ["from_status", "to_status", "changed_by", "note", "created_at"]
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Status is read-only here: change it through the API so stock and history stay correct."""

    list_display = ["id", "buyer", "farmer", "status", "payment_status", "total_amount", "created_at"]
    list_filter = ["status", "payment_status"]
    search_fields = ["buyer__email", "farmer__email"]
    raw_id_fields = ["buyer", "farmer", "cancelled_by", "buyer_requirement"]
    readonly_fields = ["status", "total_amount"]
    inlines = [OrderItemInline, OrderStatusHistoryInline]


@admin.register(OrderStatusHistory)
class OrderStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ["order", "from_status", "to_status", "changed_by", "created_at"]
    raw_id_fields = ["order", "changed_by"]
