from django.contrib import admin

from .models import ListingImage, ProduceCategory, ProduceListing


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0


@admin.register(ProduceCategory)
class ProduceCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(ProduceListing)
class ProduceListingAdmin(admin.ModelAdmin):
    list_display = ["produce_name", "farmer", "quantity_available", "unit", "price_per_unit", "quality_grade", "status"]
    list_filter = ["status", "unit", "quality_grade", "category"]
    search_fields = ["produce_name", "produce_key", "farmer__email", "farmer__display_name"]
    raw_id_fields = ["farmer"]
    readonly_fields = ["produce_key"]
    inlines = [ListingImageInline]


@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ["id", "listing", "created_at"]
    raw_id_fields = ["listing"]
