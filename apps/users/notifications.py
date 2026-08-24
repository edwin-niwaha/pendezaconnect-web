import logging

from firebase_admin import messaging

from apps.users.models import DeviceInstallation
from core.firebase import get_firebase_app

logger = logging.getLogger(__name__)

EVENT_TEMPLATES = {
    "loan_submitted": ("Loan application received", "Your loan application was submitted successfully and is awaiting review."),
    "loan_updated": ("Loan update", "Your loan application was updated."),
    "loan_disbursed": ("Loan update", "A loan disbursement was recorded."),
    "payment_updated": ("Payment update", "Your payment status was updated."),
    "savings_updated": ("Savings update", "Your savings account was updated."),
    "account_security_changed": ("Security update", "Your account security information changed."),
    "savings_request_submitted": ("Savings request received", "Your savings request was submitted and is awaiting review."),
    "sponsorship_due": ("Sponsorship reminder", "A sponsorship payment requires your attention."),
}


def send_user_notification(user_ids, event, record_id=None):
    if event not in EVENT_TEMPLATES:
        raise ValueError("Unsupported notification event.")

    installations = list(
        DeviceInstallation.objects.filter(
            user_id__in=set(user_ids),
            active=True,
            notifications_enabled=True,
        ).only("id", "push_token")[:500]
    )
    if not installations:
        return {"sent": 0, "failed": 0}

    title, body = EVENT_TEMPLATES[event]
    data = {"event": event}
    if record_id is not None:
        data["record_id"] = str(record_id)

    message = messaging.MulticastMessage(
        tokens=[installation.push_token for installation in installations],
        notification=messaging.Notification(title=title, body=body),
        data=data,
        android=messaging.AndroidConfig(
            priority="normal",
            notification=messaging.AndroidNotification(
                channel_id="account-updates",
                visibility="private",
            ),
        ),
    )
    response = messaging.send_each_for_multicast(message, app=get_firebase_app())

    invalid_ids = [
        installation.id
        for installation, result in zip(installations, response.responses)
        if not result.success and isinstance(result.exception, messaging.UnregisteredError)
    ]
    if invalid_ids:
        DeviceInstallation.objects.filter(id__in=invalid_ids).update(
            active=False,
            notifications_enabled=False,
        )
    logger.info(
        "Firebase notification event=%s sent=%s failed=%s",
        event,
        response.success_count,
        response.failure_count,
    )
    return {"sent": response.success_count, "failed": response.failure_count}
