from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view(), name="conversations"),
    path("conversations/<int:pk>/messages/", views.ConversationMessagesView.as_view(), name="messages"),
    path("conversations/<int:pk>/read/", views.MarkReadView.as_view(), name="read"),
]
