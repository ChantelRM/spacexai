from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from . import agent
from .models import AIConversation
from .serializers import (
    ActionResultSerializer,
    ChatRequestSerializer,
    ChatResponseSerializer,
    ConversationSerializer,
    MessageSerializer,
)
from .tools.registry import cancel_pending_action, confirm_pending_action


class ChatView(APIView):
    """
    Send a message to the AI assistant. Returns Grok's reply, which tools ran,
    structured results to render, and any action awaiting the user's confirmation.
    Returns 503 ``ai_service_unavailable`` if Grok cannot be reached.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle, ScopedRateThrottle]
    throttle_scope = "ai_chat"

    @extend_schema(request=ChatRequestSerializer, responses=ChatResponseSerializer)
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = agent.run_chat(
            request.user,
            serializer.validated_data["message"],
            serializer.validated_data.get("conversation_id"),
        )
        return Response(ChatResponseSerializer(result).data)


class ConversationListView(generics.ListAPIView):
    """The current user's AI conversations, most recent first."""

    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return AIConversation.objects.filter(user=self.request.user).order_by("-updated_at")


class ConversationMessagesView(generics.ListAPIView):
    """Messages in one of the current user's conversations, oldest first. 404 for others' conversations."""

    permission_classes = [IsAuthenticated]
    serializer_class = MessageSerializer

    def get_queryset(self):
        conversation = agent.get_conversation(self.request.user, self.kwargs["pk"])
        return conversation.messages.order_by("created_at", "id")


class ConfirmActionView(APIView):
    """
    Confirm an action the assistant proposed. Only the owner can confirm; it
    runs at most once. 410 if expired, 409 if already confirmed or cancelled.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=ActionResultSerializer)
    def post(self, request, pk):
        return Response(ActionResultSerializer(confirm_pending_action(request.user, pk)).data)


class CancelActionView(APIView):
    """Cancel an action the assistant proposed. Nothing is executed."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=ActionResultSerializer)
    def post(self, request, pk):
        return Response(ActionResultSerializer(cancel_pending_action(request.user, pk)).data)
