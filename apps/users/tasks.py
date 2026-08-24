import logging

from celery import shared_task

from apps.users.notifications import send_user_notification
from apps.users.notifications import EVENT_TEMPLATES
from apps.users.models import UserNotification

logger = logging.getLogger(__name__)


@shared_task(autoretry_for=(Exception,), retry_backoff=True, retry_jitter=True, max_retries=3)
def send_user_notification_task(user_ids, event, record_id=None):
    return send_user_notification(user_ids, event, record_id)


def queue_user_notification(user_ids, event, record_id=None):
    ids = list(dict.fromkeys(int(user_id) for user_id in user_ids if user_id))
    if not ids:
        return
    if event not in EVENT_TEMPLATES:
        raise ValueError("Unsupported notification event.")
    title, body = EVENT_TEMPLATES[event]
    UserNotification.objects.bulk_create(
        [UserNotification(user_id=user_id, event=event, record_id=record_id, title=title, body=body) for user_id in ids]
    )
    try:
        send_user_notification_task.delay(ids, event, record_id)
    except Exception:
        logger.exception("Could not queue Firebase notification event=%s", event)
