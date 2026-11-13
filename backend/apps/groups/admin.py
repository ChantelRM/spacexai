from django.contrib import admin

from .models import FarmerGroup, GroupMembership, GroupPost


class MembershipInline(admin.TabularInline):
    model = GroupMembership
    extra = 0
    raw_id_fields = ["farmer", "invited_by"]


@admin.register(FarmerGroup)
class FarmerGroupAdmin(admin.ModelAdmin):
    list_display = ["name", "group_type", "municipality", "province", "is_open", "created_at"]
    list_filter = ["group_type", "province", "is_open"]
    search_fields = ["name", "focus", "municipality", "town"]
    inlines = [MembershipInline]


@admin.register(GroupPost)
class GroupPostAdmin(admin.ModelAdmin):
    list_display = ["group", "author", "is_announcement", "created_at"]
    raw_id_fields = ["group", "author"]
