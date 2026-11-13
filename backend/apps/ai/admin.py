from django.contrib import admin

from .models import AIActionLog, AIConversation, AIMessage, PendingAction


class AIMessageInline(admin.TabularInline):
    model = AIMessage
    extra = 0
    fields = ["role", "tool_name", "content", "created_at"]
    readonly_fields = fields
    can_delete = False


@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "title", "updated_at"]
    search_fields = ["user__email", "title"]
    raw_id_fields = ["user"]
    inlines = [AIMessageInline]


@admin.register(AIMessage)
class AIMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "role", "tool_name", "created_at"]
    list_filter = ["role"]
    raw_id_fields = ["conversation"]


@admin.register(AIActionLog)
class AIActionLogAdmin(admin.ModelAdmin):
    """Audit trail: read-only."""

    list_display = ["created_at", "user", "tool_name", "status", "requires_confirmation", "result_summary"]
    list_filter = ["status", "tool_name", "requires_confirmation"]
    search_fields = ["user__email", "tool_name"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PendingAction)
class PendingActionAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "tool_name", "status", "expires_at", "summary"]
    list_filter = ["status", "tool_name"]
    raw_id_fields = ["user", "conversation"]
    readonly_fields = ["arguments", "result", "executed_at"]
