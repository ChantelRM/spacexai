from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardPagination

from . import services
from .models import Message


class ThreadMessageSerializer(serializers.ModelSerializer):
    sender_id = serializers.IntegerField(read_only=True)
    sender_display_name = serializers.CharField(source="sender.display_name", read_only=True)

    class Meta:
        model = Message
        fields = ["id", "sender_id", "sender_display_name", "body", "read_at", "created_at"]
        read_only_fields = fields


class ThreadSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    other_party = serializers.SerializerMethodField()
    order_id = serializers.IntegerField(allow_null=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    updated_at = serializers.DateTimeField()

    def _user(self):
        return self.context["request"].user

    def get_other_party(self, conv) -> dict:
        other = conv.other_party(self._user())
        return {"id": other.pk, "display_name": other.display_name, "role": other.role}

    def get_last_message(self, conv) -> dict | None:
        msg = conv.messages.order_by("-created_at", "-id").first()
        return ThreadMessageSerializer(msg).data if msg else None

    def get_unread_count(self, conv) -> int:
        return services.unread_count(self._user(), conv)


class StartConversationSerializer(serializers.Serializer):
    other_user_id = serializers.IntegerField()
    order_id = serializers.IntegerField(required=False, allow_null=True)
    message = serializers.CharField(required=False, allow_blank=True, max_length=4000, default="")


class SendMessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=4000)


class ConversationListView(ListAPIView):
    """Your conversations (buyer ↔ farmer), most recent first. POST to start one."""

    permission_classes = [IsAuthenticated]
    serializer_class = ThreadSerializer

    def get_queryset(self):
        return services.conversations_for(self.request.user).order_by("-updated_at")

    @extend_schema(request=StartConversationSerializer, responses={201: ThreadSerializer})
    def post(self, request):
        s = StartConversationSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        conv = services.start_conversation(request.user, **s.validated_data)
        return Response(ThreadSerializer(conv, context={"request": request}).data,
                        status=status.HTTP_201_CREATED)


class ConversationMessagesView(APIView):
    """Messages in a conversation (participants only), oldest first. POST to send."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=ThreadMessageSerializer(many=True))
    def get(self, request, pk):
        conv = services.get_conversation(request.user, pk)
        paginator = StandardPagination()
        page = paginator.paginate_queryset(conv.messages.select_related("sender").order_by("created_at", "id"),
                                           request, view=self)
        return paginator.get_paginated_response(ThreadMessageSerializer(page, many=True).data)

    @extend_schema(request=SendMessageSerializer, responses={201: ThreadMessageSerializer})
    def post(self, request, pk):
        s = SendMessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        msg = services.send_message(request.user, pk, s.validated_data["body"])
        return Response(ThreadMessageSerializer(msg).data, status=status.HTTP_201_CREATED)


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses=inline_serializer("MarkRead", {"marked_read": serializers.IntegerField()}))
    def post(self, request, pk):
        return Response({"marked_read": services.mark_read(request.user, pk)})
