from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.inventory.products.models import Inventory, ProductVariant
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import notification_service


def _level(instance):
    if instance.quantity <= 0:
        return "out"
    if instance.quantity <= instance.low_stock_threshold:
        return "low"
    return "healthy"


def _remember_previous_level(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_stock_level = None
        return
    previous = sender.objects.filter(pk=instance.pk).only("quantity", "low_stock_threshold").first()
    instance._previous_stock_level = _level(previous) if previous else None


def _notify_stock_level(instance, product, item_name):
    current = _level(instance)
    if current == "healthy" or current == getattr(instance, "_previous_stock_level", None):
        return
    event = "inventory_out_of_stock" if current == "out" else "inventory_low_stock"
    title = "Out of stock" if current == "out" else "Low stock"
    body = f"{item_name} is {title.lower()} ({instance.quantity} remaining)."
    notification_service.notify(
        NotificationRecipients.staff(),
        event,
        product.pk,
        title=title,
        body=body,
    )


@receiver(pre_save, sender=Inventory)
def inventory_before_save(sender, instance, **kwargs):
    _remember_previous_level(sender, instance)


@receiver(post_save, sender=Inventory)
def inventory_after_save(sender, instance, **kwargs):
    _notify_stock_level(instance, instance.product, instance.product.name)


@receiver(pre_save, sender=ProductVariant)
def variant_before_save(sender, instance, **kwargs):
    _remember_previous_level(sender, instance)


@receiver(post_save, sender=ProductVariant)
def variant_after_save(sender, instance, **kwargs):
    _notify_stock_level(instance, instance.product, instance.display_name)
