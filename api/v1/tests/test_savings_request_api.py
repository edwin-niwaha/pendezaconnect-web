from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from apps.client.models import Client
from apps.savings.models import SavingsAccount, SavingsTransaction
from apps.users.models import Profile


class SavingsRequestApiTests(APITestCase):
    def setUp(self):
        self.client_record = Client.objects.create(
            full_name="Savings Client",
            email="savings@example.com",
            reg_number="SAV-CLIENT",
        )
        self.account = SavingsAccount.objects.create(client=self.client_record)
        self.user = User.objects.create_user("savings-client", password="pass12345")
        Profile.objects.update_or_create(
            user=self.user,
            defaults={
                "client": self.client_record,
                "account_type": "client",
                "role": "client",
            },
        )
        self.url = f"/api/v1/clients/{self.client_record.id}/savings/requests/"
        self.client.force_authenticate(self.user)

    def test_client_can_submit_direct_deposit_for_review(self):
        response = self.client.post(
            self.url,
            {
                "amount": "40000",
                "notes": "Sent to the collection line",
                "payment_method": "mobile_money",
                "reference": "DIRECT-MM-123",
                "transaction_type": "deposit",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        request = SavingsTransaction.objects.get(reference="DIRECT-MM-123")
        self.assertEqual(request.account, self.account)
        self.assertEqual(request.amount, Decimal("40000"))
        self.assertEqual(request.status, "pending")
        self.assertEqual(request.requested_by, self.user)

    def test_duplicate_direct_deposit_reference_is_rejected(self):
        SavingsTransaction.objects.create(
            account=self.account,
            amount=Decimal("40000"),
            payment_method="mobile_money",
            reference="DIRECT-MM-123",
            status="pending",
            transaction_type="deposit",
        )

        response = self.client.post(
            self.url,
            {
                "amount": "40000",
                "payment_method": "mobile_money",
                "reference": "direct-mm-123",
                "transaction_type": "deposit",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(SavingsTransaction.objects.filter(transaction_type="deposit").count(), 1)
