from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.sponsorship.models import MoMoTransaction


class MoMoTransactionModelTests(TestCase):
    def test_create_transaction_with_all_fields(self):
        txn = MoMoTransaction.objects.create(
            reference_id="fake_ref",
            external_id="fake_ext",
            phone_number="0701234567",
            amount=10000.50,
            status="PENDING",
            donor_name="Test Donor",
            donor_email="test@example.com",
            user_id="user123",
            api_key="apikey123",
            payer_message="Thanks",
            payee_note="Donation received",
        )
        self.assertEqual(txn.reference_id, "fake_ref")
        self.assertEqual(txn.external_id, "fake_ext")
        self.assertEqual(txn.phone_number, "0701234567")
        self.assertEqual(txn.amount, 10000.50)
        self.assertEqual(txn.status, "PENDING")
        self.assertEqual(txn.donor_name, "Test Donor")
        self.assertEqual(txn.donor_email, "test@example.com")
        self.assertEqual(txn.user_id, "user123")
        self.assertEqual(txn.api_key, "apikey123")
        self.assertEqual(txn.payer_message, "Thanks")
        self.assertEqual(txn.payee_note, "Donation received")
        self.assertIsNotNone(txn.created_at)
        self.assertIsNotNone(txn.updated_at)

        # Test __str__ output
        self.assertEqual(str(txn), f"{txn.donor_name} - {txn.amount} UGX ({txn.status})")

    def test_create_transaction_with_minimal_fields(self):
        txn = MoMoTransaction.objects.create(reference_id="minimal_ref", phone_number="0712345678", amount=5000)
        # Defaults should be applied
        self.assertEqual(txn.status, "PENDING")
        self.assertEqual(txn.currency, "UGX")
        self.assertIsNone(txn.donor_name)
        self.assertIsNone(txn.donor_email)

        # __str__ should fall back to phone_number
        self.assertEqual(str(txn), f"{txn.phone_number} - {txn.amount} UGX ({txn.status})")

    def test_unique_reference_id(self):
        MoMoTransaction.objects.create(reference_id="unique_ref", phone_number="0700000000", amount=1000)
        with self.assertRaises(IntegrityError):
            MoMoTransaction.objects.create(reference_id="unique_ref", phone_number="0711111111", amount=2000)

    def test_status_choices(self):
        txn = MoMoTransaction.objects.create(reference_id="status_test", phone_number="0700000001", amount=100)
        self.assertIn(txn.status, ["PENDING", "SUCCESSFUL", "FAILED"])

        # Attempting invalid status should raise ValidationError
        txn.status = "INVALID"
        with self.assertRaises(ValidationError):
            txn.full_clean()  # triggers Django field validation

    def test_ordering_by_created_at_desc(self):
        now = timezone.now()
        txn1 = MoMoTransaction.objects.create(
            reference_id="t1",
            phone_number="0701111111",
            amount=100,
            created_at=now - timedelta(seconds=1),  # older
        )
        txn2 = MoMoTransaction.objects.create(
            reference_id="t2",
            phone_number="0702222222",
            amount=200,
            created_at=now,  # newer
        )
        all_txns = MoMoTransaction.objects.all()
        self.assertEqual(all_txns[0], txn2)
        self.assertEqual(all_txns[1], txn1)
