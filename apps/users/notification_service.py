import logging

from django.conf import settings
from django.db import transaction

from apps.users.models import UserNotification
from apps.users.notification_events import get_notification_template

logger = logging.getLogger(__name__)


class NotificationService:
    def notify(
        self,
        user_ids,
        event,
        record_id=None,
        *,
        title=None,
        body=None,
        deduplication_key="",
    ):
        ids = tuple(dict.fromkeys(int(user_id) for user_id in user_ids if user_id))
        if not ids:
            return []

        template = get_notification_template(event)
        notification_title = title or template.title
        notification_body = body or template.body
        notification_ids = []
        for user_id in ids:
            values = {
                "event": event,
                "record_id": record_id,
                "title": notification_title,
                "body": notification_body,
                "deduplication_key": deduplication_key,
            }
            if deduplication_key:
                notification, created = UserNotification.objects.get_or_create(
                    user_id=user_id,
                    deduplication_key=deduplication_key,
                    defaults=values,
                )
                if not created:
                    continue
            else:
                notification = UserNotification.objects.create(
                    user_id=user_id,
                    **values,
                )
            notification_ids.append(notification.id)

        if notification_ids and settings.NOTIFICATION_DELIVERY_ENABLED:
            transaction.on_commit(lambda: self._enqueue(notification_ids))
        return notification_ids

    @staticmethod
    def _enqueue(notification_ids):
        from apps.users.tasks import deliver_user_notifications

        try:
            # Local development commonly runs Django without a Celery worker.
            # Deliver immediately there so device push behavior matches
            # production; deployed environments continue using the queue.
            if settings.DEBUG:
                deliver_user_notifications(notification_ids)
                return
            deliver_user_notifications.delay(notification_ids)
        except Exception:
            logger.exception(
                "Could not enqueue Firebase delivery; attempting direct delivery for notifications=%s",
                notification_ids,
            )
            try:
                deliver_user_notifications(notification_ids)
            except Exception:
                logger.exception(
                    "Direct Firebase delivery also failed for notifications=%s",
                    notification_ids,
                )


notification_service = NotificationService()
