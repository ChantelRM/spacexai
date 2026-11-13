from django.urls import path

from . import views

app_name = "bulk"

urlpatterns = [
    path("", views.BulkListView.as_view(), name="list"),
    path("calculator/", views.CalculatorView.as_view(), name="calculator"),
    path("<int:pk>/", views.BulkDetailView.as_view(), name="detail"),
    path("<int:pk>/join/", views.JoinView.as_view(), name="join"),
    path("<int:pk>/leave/", views.LeaveView.as_view(), name="leave"),
    path("<int:pk>/confirm/", views.ConfirmView.as_view(), name="confirm"),
    path("<int:pk>/status/", views.StatusView.as_view(), name="status"),
]
