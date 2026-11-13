from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

app_name = "equipment"

router = SimpleRouter()
router.register("items", views.EquipmentViewSet, basename="item")

urlpatterns = [
    path("bookings/", views.BookingListView.as_view(), name="bookings"),
    path("bookings/<int:pk>/decision/", views.BookingDecisionView.as_view(), name="booking-decision"),
    path("bookings/<int:pk>/cancel/", views.BookingCancelView.as_view(), name="booking-cancel"),
    path("bookings/<int:pk>/complete/", views.BookingCompleteView.as_view(), name="booking-complete"),
    *router.urls,
]
