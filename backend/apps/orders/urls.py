from rest_framework.routers import SimpleRouter

from . import views

app_name = "orders"

router = SimpleRouter()
router.register("", views.OrderViewSet, basename="order")
urlpatterns = router.urls
