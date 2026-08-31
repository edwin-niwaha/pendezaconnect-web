from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.client.models import Client
from apps.savings.models import SavingsAccount, SavingsTransaction
from apps.users.models import Profile


class SavingsModuleTests(TestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            full_name="Savings Member",
            email="saver@example.com",
            reg_number="S001",
        )
        self.user = User.objects.create_user(
            username="saver",
            email="saver@example.com",
            password="pass12345",
        )
        Profile.objects.update_or_create(
            user=self.user,
            defaults={"role": "guest", "bio": "", "client": self.client_record},
        )
        self.staff = User.objects.create_user(username="staff", password="pass12345")
        Profile.objects.update_or_create(
            user=self.staff,
            defaults={"role": "staff", "bio": ""},
        )
        self.account = SavingsAccount.objects.create(client=self.client_record)

    def test_savings_account_auto_generates_number_and_balance(self):
        self.assertEqual(self.account.account_number, f"SAV-{self.account.pk:06d}")

        SavingsTransaction.objects.create(
            account=self.account,
            transaction_type="deposit",
            amount=Decimal("50000.00"),
            transaction_date=date(2026, 1, 1),
        )
        SavingsTransaction.objects.create(
            account=self.account,
            transaction_type="withdrawal",
            amount=Decimal("10000.00"),
            transaction_date=date(2026, 1, 2),
        )

        self.assertEqual(self.account.balance, Decimal("40000.00"))

    def test_approved_withdrawal_cannot_exceed_balance(self):
        with self.assertRaises(ValidationError):
            SavingsTransaction.objects.create(
                account=self.account,
                transaction_type="withdrawal",
                amount=Decimal("10000.00"),
                transaction_date=date(2026, 1, 2),
            )

    def test_client_cannot_request_withdrawal_above_available_balance(self):
        SavingsTransaction.objects.create(
            account=self.account,
            transaction_type="deposit",
            amount=Decimal("20000.00"),
            status="approved",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("client_savings_withdrawal_request"),
            {
                "amount": "25000.00",
                "payment_method": "mobile_money",
                "reference": "WD-OVER",
                "notes": "Too much",
            },
        )

        self.assertRedirects(response, reverse("client_savings_dashboard"))
        self.assertFalse(SavingsTransaction.objects.filter(reference="WD-OVER").exists())

    def test_client_can_submit_pending_savings_request(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("client_savings_request"),
            {
                "transaction_type": "deposit",
                "amount": "25000.00",
                "payment_method": "mobile_money",
                "reference": "MM-123",
                "notes": "Weekly savings",
            },
        )

        self.assertRedirects(response, reverse("client_savings_dashboard"))
        request_txn = SavingsTransaction.objects.get(account=self.account)
        self.assertEqual(request_txn.status, "pending")
        self.assertEqual(request_txn.requested_by, self.user)

    def test_client_direct_collection_line_deposit_waits_for_staff_approval(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("client_savings_dashboard"))
        self.assertContains(response, "+256 784 871903")
        self.assertContains(response, "2-3 working days")

        response = self.client.post(
            reverse("client_savings_deposit_request"),
            {
                "amount": "40000.00",
                "payment_method": "mobile_money",
                "reference": "DIRECT-MM-123",
                "notes": "Sent to collection line",
            },
        )

        self.assertRedirects(response, reverse("client_savings_dashboard"))
        deposit = SavingsTransaction.objects.get(reference="DIRECT-MM-123")
        self.assertEqual(deposit.transaction_type, "deposit")
        self.assertEqual(deposit.payment_method, "mobile_money")
        self.assertEqual(deposit.status, "pending")
        self.assertEqual(self.account.balance, Decimal("0.00"))

    @override_settings(
        MOMO_API_USER="momo-user",
        MOMO_API_KEY="momo-key",
        SUBSCRIPTION_KEY="sub-key",
        MOMO_CALLBACK_URL="https://example.com/callback/",
    )
    @patch("apps.savings.views.request_to_pay")
    @patch("apps.savings.views.generate_uuid")
    @patch("apps.savings.views.create_access_token")
    def test_client_mobile_money_deposit_initiates_collection(
        self,
        mock_create_access_token,
        mock_generate_uuid,
        mock_request_to_pay,
    ):
        mock_create_access_token.return_value = "access-token"
        mock_generate_uuid.return_value = "deposit-ref-123"
        mock_request_to_pay.return_value = (202, "")
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("client_savings_deposit_payment"),
            {
                "amount": "25000.00",
                "phone": "0771234567",
                "notes": "Weekly deposit",
            },
        )

        self.assertRedirects(
            response,
            reverse("client_savings_deposit_waiting") + "?ref=deposit-ref-123",
            fetch_redirect_response=False,
        )
        mock_request_to_pay.assert_called_once_with("access-token", "sub-key", "256771234567", 25000, "deposit-ref-123")
        self.assertFalse(SavingsTransaction.objects.filter(reference="deposit-ref-123").exists())
        self.assertFalse(SavingsTransaction.objects.filter(reference="deposit-ref-123-FEE").exists())
        pending_deposit = self.client.session["pending_mobile_money_savings_deposits"]["deposit-ref-123"]
        self.assertEqual(pending_deposit["amount"], "25000.00")
        self.assertEqual(pending_deposit["fee_amount"], "500.00")

    @override_settings(
        MOMO_API_USER="momo-user",
        MOMO_API_KEY="momo-key",
        SUBSCRIPTION_KEY="sub-key",
    )
    @patch("apps.savings.views.requests.get")
    @patch("apps.savings.views.create_access_token")
    def test_successful_mobile_money_deposit_updates_statement(
        self,
        mock_create_access_token,
        mock_requests_get,
    ):
        mock_create_access_token.return_value = "access-token"
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"status": "SUCCESSFUL"}
        mock_requests_get.return_value = response
        self.client.force_login(self.user)
        session = self.client.session
        session["pending_mobile_money_savings_deposits"] = {
            "deposit-ref-456": {
                "account_id": self.account.pk,
                "amount": "30000.00",
                "fee_amount": "600.00",
                "phone": "0771234567",
                "notes": "Weekly deposit",
            }
        }
        session.save()

        response = self.client.get(reverse("client_savings_deposit_status", args=["deposit-ref-456"]))

        self.assertEqual(response.json()["status"], "SUCCESSFUL")
        deposit = SavingsTransaction.objects.get(reference="deposit-ref-456")
        fee = SavingsTransaction.objects.get(reference="deposit-ref-456-FEE")
        self.assertEqual(deposit.status, "approved")
        self.assertEqual(fee.status, "approved")
        self.assertEqual(self.account.balance, Decimal("29400.00"))
        self.assertNotIn(
            "deposit-ref-456",
            self.client.session.get("pending_mobile_money_savings_deposits", {}),
        )

        statement = self.client.get(reverse("client_savings_statement"))
        self.assertContains(statement, "deposit-ref-456")
        self.assertContains(statement, "deposit-ref-456-FEE")
        self.assertContains(statement, "30,000.00")
        self.assertContains(statement, "600.00")
        self.assertContains(statement, "29,400.00")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_client_withdrawal_request_notifies_finance_team(self):
        hof = User.objects.create_user(username="hof", email="hof@example.com", password="pass12345")
        accountant = User.objects.create_user(
            username="accountant",
            email="accountant@example.com",
            password="pass12345",
        )
        Profile.objects.update_or_create(
            user=hof,
            defaults={"role": "hof", "staff_role": "hof", "bio": ""},
        )
        Profile.objects.update_or_create(
            user=accountant,
            defaults={"role": "accountant", "staff_role": "accountant", "bio": ""},
        )
        SavingsTransaction.objects.create(
            account=self.account,
            transaction_type="deposit",
            amount=Decimal("50000.00"),
            status="approved",
        )
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("client_savings_withdrawal_request"),
            {
                "amount": "15000.00",
                "payment_method": "mobile_money",
                "reference": "WD-123",
                "notes": "Need cash",
            },
        )

        self.assertRedirects(response, reverse("client_savings_dashboard"))
        request_txn = SavingsTransaction.objects.get(reference="WD-123")
        self.assertEqual(request_txn.transaction_type, "withdrawal")
        self.assertEqual(request_txn.status, "pending")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(set(mail.outbox[0].to), {"hof@example.com", "accountant@example.com"})

    def test_staff_can_approve_client_savings_request(self):
        request_txn = SavingsTransaction.objects.create(
            account=self.account,
            transaction_type="deposit",
            amount=Decimal("25000.00"),
            status="pending",
            requested_by=self.user,
        )
        self.client.force_login(self.staff)

        response = self.client.post(reverse("savings_transaction_approve", args=[request_txn.id]))

        self.assertRedirects(response, reverse("savings_account_detail", args=[self.account.id]))
        request_txn.refresh_from_db()
        self.assertEqual(request_txn.status, "approved")
        self.assertEqual(request_txn.approved_by, self.staff)
        self.assertEqual(self.account.balance, Decimal("25000.00"))

    def test_staff_and_client_savings_pages_render(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("savings_account_list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("savings_account_detail", args=[self.account.id])).status_code,
            200,
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse("client_savings_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.account.account_number)
