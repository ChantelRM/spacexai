from django.contrib import admin

from .models import (
    InsuranceProduct,
    InsuranceQuoteRequest,
    SecurityAlert,
    ServiceContribution,
    SharedServiceRequest,
)


class ContributionInline(admin.TabularInline):
    model = ServiceContribution
    extra = 0
    raw_id_fields = ["farmer"]


@admin.register(SharedServiceRequest)
class SharedServiceRequestAdmin(admin.ModelAdmin):
    list_display = ["title", "service_type", "municipality", "total_monthly_cost", "status"]
    list_filter = ["service_type", "status", "province"]
    raw_id_fields = ["organiser", "group"]
    inlines = [ContributionInline]


@admin.register(SecurityAlert)
class SecurityAlertAdmin(admin.ModelAdmin):
    list_display = ["title", "alert_type", "municipality", "author", "created_at"]
    list_filter = ["alert_type", "province"]
    raw_id_fields = ["author", "group"]


@admin.register(InsuranceProduct)
class InsuranceProductAdmin(admin.ModelAdmin):
    list_display = ["provider_name", "name", "category", "is_authorised_provider", "is_active"]
    list_filter = ["category", "is_authorised_provider", "is_active"]


@admin.register(InsuranceQuoteRequest)
class InsuranceQuoteRequestAdmin(admin.ModelAdmin):
    """Admins record quotes here after contacting providers."""

    list_display = ["farmer", "category", "product", "status", "quote_amount", "created_at"]
    list_filter = ["status", "category"]
    raw_id_fields = ["farmer", "product"]
