import logging
from datetime import timedelta

from firebase_admin import messaging

from apps.users.models import DeviceInstallation
from core.firebase import get_firebase_app

logger = logging.getLogger(__name__)


class FirebaseNotificationGateway:
    MAX_BATCH_SIZE = 500
    # Must match the immutable Android channel created by the mobile app.
    CHANNEL_ID = "account-updates-v3"

    def send(self, user_ids, title, body, data):
        installations = list(
            DeviceInstallation.objects.filter(
                user_id__in=set(user_ids),
                platform__in=(DeviceInstallation.PLATFORM_ANDROID, DeviceInstallation.PLATFORM_IOS),
                active=True,
                notifications_enabled=True,
            ).only("id", "push_token")
        )
        totals = {"sent": 0, "failed": 0}
        for start in range(0, len(installations), self.MAX_BATCH_SIZE):
            batch = installations[start : start + self.MAX_BATCH_SIZE]
            result = self._send_batch(batch, title, body, data)
            totals["sent"] += result.success_count
            totals["failed"] += result.failure_count
            self._deactivate_invalid_installations(batch, result.responses)
        return totals

    def _send_batch(self, installations, title, body, data):
        message = messaging.MulticastMessage(
            tokens=[installation.push_token for installation in installations],
            notification=messaging.Notification(title=title, body=body),
            data={key: str(value) for key, value in data.items()},
            android=messaging.AndroidConfig(
                priority="high",
                ttl=timedelta(days=1),
                notification=messaging.AndroidNotification(
                    channel_id=self.CHANNEL_ID,
                    sound="pendeza_chime",
                    visibility="private",
                ),
            ),
            apns=messaging.APNSConfig(
                headers={"apns-priority": "10"},
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound="pendeza_chime.wav",
                    ),
                ),
            ),
        )
        return messaging.send_each_for_multicast(message, app=get_firebase_app())

    @staticmethod
    def _deactivate_invalid_installations(installations, responses):
        invalid_ids = [
            installation.id
            for installation, response in zip(installations, responses)
            if not response.success and isinstance(response.exception, messaging.UnregisteredError)
        ]
        if invalid_ids:
            DeviceInstallation.objects.filter(id__in=invalid_ids).update(
                active=False,
                notifications_enabled=False,
            )


def send_user_notification(user_ids, event, record_id=None, title=None, body=None):
    from apps.users.notification_events import get_notification_template

    template = get_notification_template(event)
    payload = {"event": event}
    if record_id is not None:
        payload["record_id"] = record_id
    result = FirebaseNotificationGateway().send(
        user_ids,
        title or template.title,
        body or template.body,
        payload,
    )
    logger.info(
        "Firebase notification event=%s sent=%s failed=%s",
        event,
        result["sent"],
        result["failed"],
    )
    return result
