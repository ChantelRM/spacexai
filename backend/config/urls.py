from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.views import HealthCheckView

api_v1 = [
    path("health/", HealthCheckView.as_view(), name="health"),
    path("auth/", include("apps.accounts.urls")),
    path("locations/", include("apps.locations.urls")),
    path("ai/", include("apps.ai.urls")),
    path("farmers/", include("apps.farmers.urls")),
    path("listings/", include("apps.listings.urls")),
    path("buyers/", include("apps.buyers.urls")),
    path("recommendations/", include("apps.recommendations.urls")),
    path("orders/", include("apps.orders.urls")),
    path("messaging/", include("apps.messaging.urls")),
    path("marketplace/", include("apps.marketplace.urls")),
    path("notifications/", include("apps.core.urls")),
    path("groups/", include("apps.groups.urls")),
    path("bulk-purchases/", include("apps.bulk.urls")),
    path("transport/", include("apps.transport.urls")),
    path("services/", include("apps.services.urls")),
    path("equipment/", include("apps.equipment.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include(api_v1)),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
