from django.apps import AppConfig


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = "AI agent (Grok)"

    def ready(self):
        from .tools import definitions  # noqa: F401  (registers the tools)
