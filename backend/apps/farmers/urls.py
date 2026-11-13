from django.urls import path

from apps.recommendations.views import FarmerDashboardRecommendationsView

from . import views

app_name = "farmers"

urlpatterns = [
    path("me/profile/", views.MyFarmerProfileView.as_view(), name="my-profile"),
    path("me/recommended-buyers/", FarmerDashboardRecommendationsView.as_view(), name="recommended-buyers"),
    path("<int:pk>/", views.PublicFarmerView.as_view(), name="detail"),
]
