from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.sponsorship.models import MoMoTransaction
from apps.sponsorship.momo_prod import request_to_pay


@override_settings(MOMO_PAYMENT_INITIATION_ENABLED=False)
class PaymentPauseTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("apps.sponsorship.views.request_to_pay")
    @patch("apps.sponsorship.views.create_access_token")
    def test_page_and_direct_posts_are_paused_for_every_currency(self, token, pay):
        for currency in ("UGX", "USD", ""):
            for method in ("get", "post"):
                with self.subTest(currency=currency, method=method):
                    response = getattr(self.client, method)(
                        reverse("initiate_payment") + "?currency=" + currency,
                        {"phone": "0771234567", "amount": "5000"},
                    )
                    self.assertContains(response, "payments are paused", status_code=503)
                    self.assertTemplateUsed(response, "sponsorship/payment_paused.html")
                    self.assertNotContains(response, "<form", status_code=503)
                    self.assertNotContains(response, "<script", status_code=503)
                    self.assertIn("no-store", response["Cache-Control"])
        token.assert_not_called()
        pay.assert_not_called()
        self.assertFalse(MoMoTransaction.objects.exists())

    @patch("api.v1.views.payment_viewsets.request_to_pay")
    @patch("api.v1.views.payment_viewsets.create_access_token")
    def test_api_is_paused_before_validation_or_transaction_creation(self, token, pay):
        for payload in ({}, {"phone": "0771234567", "amount": 5000}):
            with self.subTest(payload=payload):
                response = self.client.post(
                    "/api/v1/payments/mobile-money/initiate/", payload, content_type="application/json"
                )
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["code"], "payment_initiation_paused")
                self.assertEqual(response["Cache-Control"], "no-store")
        token.assert_not_called()
        pay.assert_not_called()
        self.assertFalse(MoMoTransaction.objects.exists())

    @patch("apps.sponsorship.momo_prod.requests.post")
    def test_provider_helper_cannot_bypass_pause(self, post):
        status, message = request_to_pay("unused", "unused", "0771234567", 5000, "unused")
        self.assertEqual(status, 503)
        self.assertIn("paused", message)
        post.assert_not_called()

    def test_existing_transaction_status_stays_available(self):
        transaction = MoMoTransaction.objects.create(
            reference_id="550e8400-e29b-41d4-a716-446655440000",
            external_id="existing-payment",
            amount=5000,
            status="SUCCESSFUL",
        )
        response = self.client.get(f"/api/v1/payments/mobile-money/{transaction.reference_id}/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "SUCCESSFUL")

    def test_existing_transaction_callback_stays_available(self):
        transaction = MoMoTransaction.objects.create(
            reference_id="existing-ref", external_id="existing-payment", amount=5000, status="PENDING"
        )
        response = self.client.post(
            reverse("momo_callback"),
            {"externalId": "existing-payment", "status": "SUCCESSFUL", "amount": "5000"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        transaction.refresh_from_db()
        self.assertEqual(transaction.status, "SUCCESSFUL")
