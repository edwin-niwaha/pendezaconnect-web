from django.apps import AppConfig


class SavingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.savings"

    def ready(self):
        import apps.savings.signals  # noqa: F401
