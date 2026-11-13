from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

app_name = "listings"

router = SimpleRouter()
router.register("mine", views.MyListingViewSet, basename="mine")

urlpatterns = [
    path("categories/", views.CategoryListView.as_view(), name="categories"),
    *router.urls,
]
