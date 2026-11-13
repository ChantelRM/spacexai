from django.apps import AppConfig


class SharedServicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.services"
    label = "shared_services"
    verbose_name = "Security & insurance"
