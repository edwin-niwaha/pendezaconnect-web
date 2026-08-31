from unittest.mock import patch

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from apps.sponsorship.models import MoMoTransaction


@override_settings(
    MOMO_API_USER="test-user",
    MOMO_API_KEY="test-key",
    SUBSCRIPTION_KEY="test-subscription",
)
class PublicMobileMoneyApiTests(APITestCase):
    initiate_url = "/api/v1/payments/mobile-money/initiate/"

    @patch("api.v1.views.payment_viewsets.request_to_pay", return_value=(202, {}))
    @patch("api.v1.views.payment_viewsets.create_access_token", return_value="token")
    def test_anonymous_visitor_can_initiate_payment(self, _create_token, _request_to_pay):
        response = self.client.post(
            self.initiate_url,
            {
                "amount": 340000,
                "phone": "0771234567",
                "name": "Public donor",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["amount"], 340000)
        self.assertEqual(MoMoTransaction.objects.count(), 1)

    @patch("api.v1.views.payment_viewsets.request_to_pay", return_value=(202, {}))
    @patch("api.v1.views.payment_viewsets.create_access_token", return_value="token")
    def test_expired_bearer_token_does_not_block_public_payment(self, _create_token, _request_to_pay):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired-token")

        response = self.client.post(
            self.initiate_url,
            {"amount": 5000, "phone": "0771234567"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

    def test_anonymous_visitor_can_check_payment_status(self):
        transaction = MoMoTransaction.objects.create(
            reference_id="550e8400-e29b-41d4-a716-446655440000",
            external_id="550e8400-e29b-41d4-a716-446655440000",
            phone_number="0771234567",
            amount=340000,
            currency="UGX",
            status="SUCCESSFUL",
        )

        response = self.client.get(f"/api/v1/payments/mobile-money/{transaction.reference_id}/status/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "SUCCESSFUL")
