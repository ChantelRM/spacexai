from django.urls import path
from rest_framework.routers import SimpleRouter

from apps.recommendations.views import BuyerDashboardRecommendationsView

from . import views

app_name = "buyers"

router = SimpleRouter()
router.register("requirements", views.RequirementViewSet, basename="requirements")

urlpatterns = [
    path("me/profile/", views.MyBuyerProfileView.as_view(), name="my-profile"),
    path("me/recommended-farmers/", BuyerDashboardRecommendationsView.as_view(), name="recommended-farmers"),
    path("<int:pk>/", views.PublicBuyerView.as_view(), name="detail"),
    *router.urls,
]
