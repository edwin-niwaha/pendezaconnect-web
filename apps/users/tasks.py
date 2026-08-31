from celery import shared_task

from apps.users.models import UserNotification
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import notification_service
from apps.users.notifications import send_user_notification


@shared_task(autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def deliver_user_notifications(notification_ids):
    notifications = list(UserNotification.objects.filter(id__in=notification_ids).order_by("id"))
    if not notifications:
        return {"sent": 0, "failed": 0}
    first = notifications[0]
    return send_user_notification(
        [notification.user_id for notification in notifications],
        first.event,
        first.record_id,
        title=first.title,
        body=first.body,
    )


def queue_user_notification(
    user_ids,
    event,
    record_id=None,
    *,
    title=None,
    body=None,
    deduplication_key="",
):
    return notification_service.notify(
        user_ids,
        event,
        record_id,
        title=title,
        body=body,
        deduplication_key=deduplication_key,
    )


def staff_notification_user_ids():
    return NotificationRecipients.staff()


def client_notification_user_ids(client_id):
    return NotificationRecipients.clients(client_id)


def sponsor_notification_user_ids(sponsor_id):
    return NotificationRecipients.sponsors(sponsor_id)
