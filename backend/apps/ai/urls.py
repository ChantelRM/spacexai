from django.urls import path

from . import views

app_name = "ai"

urlpatterns = [
    path("chat/", views.ChatView.as_view(), name="chat"),
    path("conversations/", views.ConversationListView.as_view(), name="conversations"),
    path("conversations/<uuid:pk>/messages/", views.ConversationMessagesView.as_view(), name="conversation-messages"),
    path("actions/<uuid:pk>/confirm/", views.ConfirmActionView.as_view(), name="action-confirm"),
    path("actions/<uuid:pk>/cancel/", views.CancelActionView.as_view(), name="action-cancel"),
]
