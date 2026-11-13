from django.urls import path

from . import views

app_name = "shared_services"

urlpatterns = [
    path("security/", views.SharedServiceListView.as_view(), name="security"),
    path("security/<int:pk>/", views.SharedServiceDetailView.as_view(), name="security-detail"),
    path("security/<int:pk>/join/", views.SharedServiceJoinView.as_view(), name="security-join"),
    path("security/<int:pk>/leave/", views.SharedServiceLeaveView.as_view(), name="security-leave"),
    path("security/<int:pk>/cost/", views.SharedServiceCostView.as_view(), name="security-cost"),
    path("security/<int:pk>/confirm/", views.SharedServiceConfirmView.as_view(), name="security-confirm"),
    path("security-alerts/", views.SecurityAlertListView.as_view(), name="alerts"),
    path("insurance/products/", views.InsuranceProductListView.as_view(), name="insurance-products"),
    path("insurance/quote-requests/", views.QuoteRequestListView.as_view(), name="insurance-quotes"),
]
