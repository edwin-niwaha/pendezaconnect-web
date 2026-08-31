from django.apps import AppConfig


class ProductsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.inventory.products"

    def ready(self):
        from apps.inventory.products import signals  # noqa: F401
