from django.urls import path

from . import views

app_name = "marketplace"

urlpatterns = [
    path("listings/", views.ListingSearchView.as_view(), name="listings"),
    path("listings/<int:pk>/", views.ListingDetailView.as_view(), name="listing-detail"),
    path("compare/", views.CompareView.as_view(), name="compare"),
    path("farmers/", views.FarmerDiscoveryView.as_view(), name="farmers"),
]
