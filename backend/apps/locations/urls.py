from django.urls import path

from . import views

app_name = "locations"

urlpatterns = [
    path("me/", views.MyLocationView.as_view(), name="me"),
]
