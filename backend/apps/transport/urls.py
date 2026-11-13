from django.urls import path

from . import views

app_name = "transport"

urlpatterns = [
    path("", views.TransportListView.as_view(), name="list"),
    path("<int:pk>/", views.TransportDetailView.as_view(), name="detail"),
    path("<int:pk>/join/", views.JoinView.as_view(), name="join"),
    path("<int:pk>/leave/", views.LeaveView.as_view(), name="leave"),
    path("<int:pk>/cost/", views.CostView.as_view(), name="cost"),
    path("<int:pk>/confirm/", views.ConfirmView.as_view(), name="confirm"),
    path("<int:pk>/status/", views.StatusView.as_view(), name="status"),
]
