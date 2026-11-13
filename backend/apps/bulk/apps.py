from django.apps import AppConfig


class BulkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bulk"
    label = "bulk"
    verbose_name = "Bulk purchasing"
