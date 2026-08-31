from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.savings.models import SavingsAccount, SavingsTransaction
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import notification_service

ACCOUNT_FIELDS = ("client_id", "status")
TRANSACTION_FIELDS = (
    "account_id",
    "transaction_type",
    "amount",
    "transaction_date",
    "status",
)


def _remember_values(sender, instance, fields):
    instance._notification_previous_values = (
        sender.objects.filter(pk=instance.pk).values_list(*fields).first() if instance.pk else None
    )


def _changed(instance, fields, created):
    if created:
        return True
    previous = getattr(instance, "_notification_previous_values", None)
    current = tuple(getattr(instance, field) for field in fields)
    return previous is not None and previous != current


def _notify_savings_change(client_id, account_id, notify_client):
    notification_service.notify(
        NotificationRecipients.staff(),
        "client_savings_changed",
        account_id,
    )
    if notify_client:
        notification_service.notify(
            NotificationRecipients.clients(client_id),
            "savings_updated",
            account_id,
        )


@receiver(pre_save, sender=SavingsAccount)
def remember_previous_savings_account(sender, instance, **kwargs):
    _remember_values(sender, instance, ACCOUNT_FIELDS)


@receiver(post_save, sender=SavingsAccount)
def notify_savings_account_change(sender, instance, created, **kwargs):
    if _changed(instance, ACCOUNT_FIELDS, created):
        _notify_savings_change(
            instance.client_id,
            instance.pk,
            notify_client=not created,
        )


@receiver(pre_save, sender=SavingsTransaction)
def remember_previous_savings_transaction(sender, instance, **kwargs):
    _remember_values(sender, instance, TRANSACTION_FIELDS)


@receiver(post_save, sender=SavingsTransaction)
def notify_savings_transaction_change(sender, instance, created, **kwargs):
    if _changed(instance, TRANSACTION_FIELDS, created):
        _notify_savings_change(
            instance.account.client_id,
            instance.account_id,
            notify_client=not created or instance.status == "approved",
        )
