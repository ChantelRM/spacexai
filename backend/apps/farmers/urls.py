from django.urls import path

from . import views

app_name = "farmers"

urlpatterns = [
    path("me/profile/", views.MyFarmerProfileView.as_view(), name="my-profile"),
    path("<int:pk>/", views.PublicFarmerView.as_view(), name="detail"),
]
