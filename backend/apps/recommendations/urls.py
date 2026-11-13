from django.urls import path

from . import views

app_name = "recommendations"

urlpatterns = [
    path("farmers/", views.RecommendFarmersView.as_view(), name="farmers"),
]
