import csv
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.test import Client as WebClient
from django.test import TestCase
from django.urls import reverse

from apps.client.models import Client
from apps.loans.models import Loan
from apps.users.models import Profile


class ClientStatusTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="status-manager")
        Profile.objects.create(user=self.manager, role="manager")
        self.client.force_login(self.manager)
        self.active = Client.objects.create(full_name="Active Example", reg_number="ACTIVE-01", branch="Central")
        self.inactive = Client.objects.create(full_name="Inactive Example", reg_number="INACTIVE-01", is_active=False)
        self.url = reverse("change_client_status", args=[self.active.pk])

    def test_deactivate_and_reactivate_preserve_client_and_loans(self):
        loan = Loan.objects.bulk_create([Loan(
            borrower=self.active, principal_amount=Decimal("1000"), total_interest=Decimal("100"),
            interest_rate=Decimal("10"), start_date=date(2026, 1, 1),
            disbursement_date=date(2026, 1, 1), loan_period_months=10, status="disbursed",
        )])[0]
        self.assertRedirects(self.client.post(self.url, {"action": "deactivate"}), reverse("client_list"))
        self.active.refresh_from_db()
        self.assertFalse(self.active.is_active)
        self.assertEqual(self.active.status_changed_by, self.manager)
        self.assertIsNotNone(self.active.status_changed_at)
        loan.refresh_from_db()
        self.assertEqual(loan.borrower_id, self.active.pk)
        self.assertEqual(loan.principal_amount, Decimal("1000"))
        self.assertEqual(loan.status, "disbursed")
        self.assertContains(self.client.get(reverse("client_profile", args=[self.active.pk])), "Inactive")
        response = self.client.get(reverse("loans:loan_aging_report"), {"end_date": "2026-03-01"})
        self.assertEqual(response.context["totals"]["count"], 1)
        self.assertRedirects(
            self.client.post(self.url, {"action": "reactivate", "return_to": "inactive"}),
            reverse("inactive_clients_report"),
        )
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_active)
        self.assertTrue(Loan.objects.filter(pk=loan.pk).exists())

    def test_directory_and_inactive_report_have_correct_cohorts(self):
        response = self.client.get(reverse("client_list"))
        self.assertEqual(list(response.context["records"]), [self.active])
        response = self.client.get(reverse("client_list"), {"status": "all"})
        self.assertEqual(response.context["records"].paginator.count, 2)
        response = self.client.get(reverse("inactive_clients_report"), {"status": "active"})
        self.assertEqual(list(response.context["records"]), [self.inactive])
        self.assertContains(response, "Reactivate")
        self.assertContains(response, "Inactive clients report")
        response = self.client.get(reverse("inactive_clients_report"), {"search": "missing"})
        self.assertEqual(response.context["records"].paginator.count, 0)

    def test_inactive_csv_matches_search_and_includes_status(self):
        self.client.post(self.url, {"action": "deactivate"})
        response = self.client.get(reverse("inactive_clients_report"), {"export": "csv", "search": "Central"})
        rows = list(csv.DictReader(StringIO(response.content.decode())))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reg_number"], "ACTIVE-01")
        self.assertEqual(rows[0]["is_active"], "False")
        self.assertEqual(rows[0]["status_changed_by"], "status-manager")
        self.assertTrue(rows[0]["status_changed_at"])
        self.assertIn("inactive_clients.csv", response["Content-Disposition"])

    def test_duplicate_action_preserves_original_audit_timestamp(self):
        self.client.post(self.url, {"action": "deactivate"})
        self.active.refresh_from_db()
        changed_at = self.active.status_changed_at
        self.client.post(self.url, {"action": "deactivate"})
        self.active.refresh_from_db()
        self.assertEqual(self.active.status_changed_at, changed_at)

    def test_status_changes_require_post_and_valid_action(self):
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.assertEqual(self.client.post(self.url, {"action": "invalid"}).status_code, 400)
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_active)

    def test_staff_can_read_but_cannot_change_status(self):
        staff = User.objects.create_user(username="status-staff")
        Profile.objects.create(user=staff, role="staff")
        self.client.force_login(staff)
        response = self.client.get(reverse("inactive_clients_report"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, ">Reactivate</button>")
        self.assertEqual(self.client.post(self.url, {"action": "deactivate"}).status_code, 403)
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_active)

    def test_unauthenticated_and_csrf_requests_cannot_change_status(self):
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"action": "deactivate"}).status_code, 302)
        secure_client = WebClient(enforce_csrf_checks=True)
        secure_client.force_login(self.manager)
        self.assertEqual(secure_client.post(self.url, {"action": "deactivate"}).status_code, 403)
        self.active.refresh_from_db()
        self.assertTrue(self.active.is_active)
