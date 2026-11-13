from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="notifications"),
    path("unread-count/", views.NotificationUnreadCountView.as_view(), name="notifications-unread"),
    path("read-all/", views.NotificationReadAllView.as_view(), name="notifications-read-all"),
    path("<int:pk>/read/", views.NotificationReadView.as_view(), name="notification-read"),
]
