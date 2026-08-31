from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.child.models import Child
from apps.sponsor.models import Sponsor
from apps.sponsorship.models import ChildSponsorship
from apps.sponsorship.reminders import SponsorshipReminderService
from apps.users.models import DeviceInstallation, Profile, UserNotification
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import NotificationService
from apps.users.notifications import FirebaseNotificationGateway


class NotificationRecipientTests(TestCase):
    def test_staff_policy_supports_current_and_legacy_roles(self):
        current = User.objects.create_user("current_staff")
        legacy = User.objects.create_user("legacy_staff")
        outsider = User.objects.create_user("client_user")
        Profile.objects.create(
            user=current,
            account_type="staff",
            staff_role="accountant",
            role="guest",
            bio="",
        )
        Profile.objects.create(
            user=legacy,
            account_type="guest",
            staff_role="",
            role="manager",
            bio="",
        )
        Profile.objects.create(
            user=outsider,
            account_type="client",
            role="client",
            bio="",
        )

        self.assertEqual(
            set(NotificationRecipients.staff()),
            {current.id, legacy.id},
        )

    def test_staff_roles_targets_only_requested_workflow_stage(self):
        boo = User.objects.create_user("boo_user")
        hof = User.objects.create_user("hof_user")
        ed = User.objects.create_user("ed_user")
        Profile.objects.create(user=boo, account_type="staff", staff_role="boo", role="boo", bio="")
        Profile.objects.create(user=hof, account_type="staff", staff_role="hof", role="hof", bio="")
        Profile.objects.create(user=ed, account_type="staff", staff_role="ed", role="ed", bio="")

        self.assertEqual(set(NotificationRecipients.staff_roles("hof")), {hof.id})
        self.assertEqual(set(NotificationRecipients.staff_roles("boo", "ed")), {boo.id, ed.id})


class NotificationServiceTests(TestCase):
    @override_settings(NOTIFICATION_DELIVERY_ENABLED=True)
    def test_persists_once_and_enqueues_after_commit(self):
        user = User.objects.create_user("notified_user")
        service = NotificationService()

        with patch.object(service, "_enqueue") as enqueue:
            with self.captureOnCommitCallbacks(execute=True):
                first = service.notify(
                    [user.id, user.id],
                    "sponsorship_due",
                    7,
                    deduplication_key="sponsorship-due:7:2026-08",
                )
                second = service.notify(
                    [user.id],
                    "sponsorship_due",
                    7,
                    deduplication_key="sponsorship-due:7:2026-08",
                )

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(UserNotification.objects.filter(user=user).count(), 1)
        enqueue.assert_called_once_with(first)

    def test_rejects_unknown_event(self):
        user = User.objects.create_user("unknown_event_user")
        with self.assertRaisesRegex(ValueError, "Unsupported notification event"):
            NotificationService().notify([user.id], "not-a-real-event")

    @override_settings(DEBUG=False)
    def test_falls_back_to_direct_delivery_when_queue_is_unavailable(self):
        with patch(
            "apps.users.tasks.deliver_user_notifications.delay", side_effect=ConnectionError("Redis unavailable")
        ):
            with patch("apps.users.tasks.deliver_user_notifications.run") as direct:
                NotificationService._enqueue([11, 12])

        direct.assert_called_once_with([11, 12])


class FirebaseNotificationGatewayTests(TestCase):
    def test_batches_android_installations_and_excludes_ios_tokens(self):
        android = [SimpleNamespace(id=index, push_token=f"token-{index}") for index in range(501)]
        queryset = Mock()
        queryset.only.return_value = android
        response = SimpleNamespace(success_count=1, failure_count=0, responses=[])
        gateway = FirebaseNotificationGateway()

        with patch.object(DeviceInstallation.objects, "filter", return_value=queryset) as filtered:
            with patch.object(gateway, "_send_batch", return_value=response) as send_batch:
                result = gateway.send([1], "Title", "Body", {"event": "loan_updated"})

        self.assertEqual(send_batch.call_count, 2)
        self.assertEqual(len(send_batch.call_args_list[0].args[0]), 500)
        self.assertEqual(len(send_batch.call_args_list[1].args[0]), 1)
        self.assertEqual(result, {"sent": 2, "failed": 0})
        self.assertEqual(
            set(filtered.call_args.kwargs["platform__in"]),
            {DeviceInstallation.PLATFORM_ANDROID, DeviceInstallation.PLATFORM_IOS},
        )


class SponsorshipReminderTests(TestCase):
    def test_monthly_reminder_targets_linked_sponsor_once(self):
        sponsor = Sponsor.objects.create(
            first_name="Grace",
            last_name="Sponsor",
            gender="Female",
            email="grace.sponsor@example.com",
        )
        child = Child.objects.create(full_name="Hope Child", gender="Female")
        ChildSponsorship.objects.create(
            sponsor=sponsor,
            child=child,
            start_date=timezone.localdate(),
            is_active=True,
        )
        user = User.objects.create_user("sponsor_user")
        Profile.objects.create(
            user=user,
            sponsor=sponsor,
            account_type="sponsor",
            role="sponsor",
            bio="",
        )
        service = SponsorshipReminderService()

        first = service.send_monthly_due()
        second = service.send_monthly_due()

        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        notification = UserNotification.objects.get(user=user)
        self.assertEqual(notification.event, "sponsorship_due")
        self.assertEqual(notification.record_id, sponsor.id)
