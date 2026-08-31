from django.apps import AppConfig


class LoansConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.loans"

    def ready(self):
        import apps.loans.signals  # noqa: F401
