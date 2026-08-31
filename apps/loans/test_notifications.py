from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.loans.signals import notify_loan_status_change


class LoanNotificationRoutingTests(SimpleTestCase):
    def _assert_stage(self, status, expected_roles, expected_event):
        loan = SimpleNamespace(pk=42, status=status, borrower_id=7, _notification_previous_status="previous")
        with patch("apps.loans.signals.NotificationRecipients.staff_roles", return_value=[10]) as recipients:
            with patch("apps.loans.signals.NotificationRecipients.clients", return_value=[]):
                with patch("apps.loans.signals.notification_service.notify") as notify:
                    notify_loan_status_change(sender=None, instance=loan, created=False)
        recipients.assert_called_once_with(*expected_roles)
        self.assertEqual(notify.call_args_list[0].args[:3], ([10], expected_event, 42))

    def test_routes_each_approval_stage_to_its_owner(self):
        self._assert_stage("pending", ("boo",), "loan_approval_required")
        self._assert_stage("boo_approved", ("hof",), "loan_approval_required")
        self._assert_stage("hof_approved", ("ed",), "loan_approval_required")
        self._assert_stage("approved", ("administrator", "manager"), "loan_disbursement_required")
