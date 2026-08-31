from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.loans.models import Loan
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import notification_service

APPROVAL_STAGE_NOTIFICATIONS = {
    "pending": (
        ("boo",),
        "loan_approval_required",
        "Loan awaiting BOO review",
        "A new loan application is ready for BOO review.",
    ),
    "boo_approved": (
        ("hof",),
        "loan_approval_required",
        "Loan awaiting HOF review",
        "BOO approved a loan. It is now ready for HOF review.",
    ),
    "hof_approved": (
        ("ed",),
        "loan_approval_required",
        "Loan awaiting ED review",
        "HOF approved a loan. It is now ready for ED review.",
    ),
    "approved": (
        ("administrator", "manager"),
        "loan_disbursement_required",
        "Loan ready for disbursement",
        "A loan completed all approval stages and is ready for disbursement.",
    ),
}


@receiver(pre_save, sender=Loan)
def remember_previous_loan_status(sender, instance, **kwargs):
    instance._notification_previous_status = (
        sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first() if instance.pk else None
    )


@receiver(post_save, sender=Loan)
def notify_loan_status_change(sender, instance, created, **kwargs):
    previous_status = getattr(instance, "_notification_previous_status", None)
    if not created and previous_status == instance.status:
        return

    stage = APPROVAL_STAGE_NOTIFICATIONS.get(instance.status)
    if stage:
        roles, event, title, body = stage
        notification_service.notify(
            NotificationRecipients.staff_roles(*roles),
            event,
            instance.pk,
            title=title,
            body=body,
        )
    if created:
        return

    client_event = "loan_disbursed" if instance.status == "disbursed" else "loan_updated"
    notification_service.notify(
        NotificationRecipients.clients(instance.borrower_id),
        client_event,
        instance.pk,
    )
