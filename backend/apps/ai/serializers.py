from django.conf import settings
from rest_framework import serializers

from .models import AIConversation, AIMessage


class ChatRequestSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField(required=False, allow_null=True,
                                            help_text="Omit to start a new conversation.")
    message = serializers.CharField(max_length=settings.AI_MAX_MESSAGE_LENGTH, trim_whitespace=True)


class ToolCallSummarySerializer(serializers.Serializer):
    name = serializers.CharField()
    status = serializers.CharField(help_text="success | denied | invalid | error | pending_confirmation")


class PendingActionBriefSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    tool_name = serializers.CharField()
    summary = serializers.CharField()
    expires_at = serializers.DateTimeField()


class ChatResponseSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()
    reply = serializers.CharField()
    tool_calls = ToolCallSummarySerializer(many=True)
    data = serializers.DictField(help_text="Successful tool results keyed by tool name, for rendering as cards.")
    pending_action = PendingActionBriefSerializer(allow_null=True)


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIConversation
        fields = ["id", "title", "created_at", "updated_at"]


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIMessage
        fields = ["id", "role", "content", "tool_name", "tool_call_id", "created_at"]


class ActionResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    tool_name = serializers.CharField()
    summary = serializers.CharField()
    executed_at = serializers.DateTimeField(allow_null=True)
    result = serializers.DictField(allow_null=True)
