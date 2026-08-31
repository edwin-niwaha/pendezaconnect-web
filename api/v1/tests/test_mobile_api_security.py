import base64
from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth

from apps.client.models import Client
from apps.finance.models import Payment, SupportProgram
from apps.loans.models import ChartOfAccounts, Loan
from apps.savings.models import SavingsAccount, SavingsTransaction
from apps.sponsor.models import Sponsor
from apps.staff.models import Staff
from apps.users.models import DeviceInstallation, Profile, UserNotification


class MobileApiOwnershipTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client_a = Client.objects.create(
            full_name="Client Alpha",
            email="alpha@example.com",
            reg_number="C001",
        )
        cls.client_b = Client.objects.create(
            full_name="Client Beta",
            email="beta@example.com",
            reg_number="C002",
        )
        cls.sponsor_a = Sponsor.objects.create(
            first_name="Sponsor",
            last_name="Alpha",
            gender="Male",
            email="sponsor.alpha@example.com",
        )
        cls.sponsor_b = Sponsor.objects.create(
            first_name="Sponsor",
            last_name="Beta",
            gender="Female",
            email="sponsor.beta@example.com",
        )
        cls.program, _ = SupportProgram.objects.get_or_create(
            code=SupportProgram.GENERAL_SUPPORT,
            defaults={"name": "General Support"},
        )
        cls.loan_account, _ = ChartOfAccounts.objects.get_or_create(
            account_number="1050",
            defaults={
                "account_name": "Loan Receivable",
                "account_type": "asset",
                "description": "Default loan account for mobile API tests.",
            },
        )
        cls.loan_a = Loan.objects.create(
            borrower=cls.client_a,
            principal_amount=Decimal("100000.00"),
            interest_rate=Decimal("10.00"),
            total_interest=Decimal("10000.00"),
            loan_period_months=10,
            start_date=date(2026, 1, 1),
            status="pending",
        )
        cls.loan_b = Loan.objects.create(
            borrower=cls.client_b,
            principal_amount=Decimal("200000.00"),
            interest_rate=Decimal("10.00"),
            total_interest=Decimal("20000.00"),
            loan_period_months=10,
            start_date=date(2026, 1, 1),
            status="pending",
        )
        cls.savings_a = SavingsAccount.objects.create(client=cls.client_a)
        cls.savings_b = SavingsAccount.objects.create(client=cls.client_b)
        cls.savings_txn_a = SavingsTransaction.objects.create(
            account=cls.savings_a,
            transaction_type="deposit",
            amount=Decimal("50000.00"),
        )
        cls.savings_txn_b = SavingsTransaction.objects.create(
            account=cls.savings_b,
            transaction_type="deposit",
            amount=Decimal("75000.00"),
        )
        cls.payment_a = Payment.objects.create(
            sponsor=cls.sponsor_a,
            program=cls.program,
            amount=Decimal("150000.00"),
            payment_date=date(2026, 1, 2),
            reference="PAY-A",
        )
        cls.payment_b = Payment.objects.create(
            sponsor=cls.sponsor_b,
            program=cls.program,
            amount=Decimal("250000.00"),
            payment_date=date(2026, 1, 3),
            reference="PAY-B",
        )
        cls.staff_record = Staff.objects.create(
            first_name="Staff",
            last_name="Member",
            gender="Male",
            email="staff.member@example.com",
            job_title="Officer",
        )

        cls.client_user = User.objects.create_user("client_user", password="pass12345")
        Profile.objects.update_or_create(
            user=cls.client_user,
            defaults={"client": cls.client_a, "account_type": "client", "role": "client"},
        )

        cls.sponsor_user = User.objects.create_user("sponsor_user", password="pass12345")
        Profile.objects.update_or_create(
            user=cls.sponsor_user,
            defaults={"sponsor": cls.sponsor_a, "account_type": "sponsor", "role": "sponsor"},
        )

        cls.staff_user = User.objects.create_user("staff_user", password="pass12345")
        Profile.objects.update_or_create(
            user=cls.staff_user,
            defaults={"account_type": "staff", "staff_role": "manager", "role": "manager"},
        )

    def ids_from_response(self, response):
        data = response.data
        if isinstance(data, dict) and "results" in data:
            data = data["results"]
        return {item["id"] for item in data}

    def test_unauthenticated_requests_are_rejected(self):
        response = self.client.get(reverse("mobile-clients-list"))
        self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    def test_list_responses_use_paginated_contract(self):
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(reverse("mobile-clients-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("count", response.data)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("results", response.data)
        self.assertGreaterEqual(response.data["count"], 1)
        self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_list_pagination_limits_first_page(self):
        for index in range(25):
            Client.objects.create(
                full_name=f"Extra Client {index}",
                email=f"extra{index}@example.com",
                reg_number=f"X{index:03d}",
            )
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(reverse("mobile-clients-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreater(response.data["count"], 20)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])

    def test_search_still_filters_paginated_lists(self):
        self.client.force_authenticate(self.staff_user)

        response = self.client.get(reverse("mobile-clients-list"), {"search": "Alpha"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids_from_response(response), {self.client_a.id})

    def test_client_only_sees_linked_client_loans_and_savings(self):
        self.client.force_authenticate(self.client_user)

        response = self.client.get(reverse("mobile-loans-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids_from_response(response), {self.loan_a.id})

        response = self.client.get(reverse("mobile-clients-loans", args=[self.client_b.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        response = self.client.get(reverse("mobile-clients-savings", args=[self.client_a.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item["id"] for item in response.data["accounts"]}, {self.savings_a.id})
        self.assertEqual({item["id"] for item in response.data["transactions"]}, {self.savings_txn_a.id})

    def test_sponsor_only_sees_linked_payments(self):
        self.client.force_authenticate(self.sponsor_user)

        response = self.client.get(reverse("mobile-payments-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.ids_from_response(response), {self.payment_a.id})

        response = self.client.get(reverse("mobile-sponsors-payments", args=[self.sponsor_b.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_can_access_operational_lists(self):
        self.client.force_authenticate(self.staff_user)

        for route in ("mobile-clients-list", "mobile-sponsors-list", "mobile-staff-list"):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_client_cannot_change_own_profile_photo(self):
        self.client.force_authenticate(self.client_user)
        url = reverse("mobile-clients-photos", args=[self.client_a.id])

        upload_response = self.client.post(url, {}, format="multipart")
        delete_response = self.client.delete(url)

        self.assertEqual(upload_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("apps.staff.models.cloudinary.uploader.upload")
    def test_staff_can_upload_staff_photo(self, mock_upload):
        mock_upload.return_value = {"url": "https://res.cloudinary.com/demo/staff/photo.jpg"}
        self.client.force_authenticate(self.staff_user)
        image = SimpleUploadedFile(
            "staff.png",
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
            ),
            content_type="image/png",
        )

        response = self.client.post(
            reverse("mobile-staff-photos", args=[self.staff_record.id]),
            {"picture": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["current_picture_url"], "https://res.cloudinary.com/demo/staff/photo.jpg")
        mock_upload.assert_called_once()

    def test_staff_photo_upload_rejects_invalid_image(self):
        self.client.force_authenticate(self.staff_user)
        image = SimpleUploadedFile("staff.jpg", b"fake-image-data", content_type="image/jpeg")

        response = self.client.post(
            reverse("mobile-staff-photos", args=[self.staff_record.id]),
            {"picture": image},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("picture", response.data)

    def test_staff_photo_upload_requires_picture(self):
        self.client.force_authenticate(self.staff_user)

        response = self.client.post(reverse("mobile-staff-photos", args=[self.staff_record.id]), {}, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("picture", response.data)

    def test_staff_can_delete_staff_photo(self):
        self.staff_record.picture = "https://res.cloudinary.com/demo/staff/photo.jpg"
        self.staff_record.save(update_fields=["picture", "updated_at"])
        self.client.force_authenticate(self.staff_user)

        response = self.client.delete(reverse("mobile-staff-photos", args=[self.staff_record.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["current_picture_url"])


class MobileGoogleLoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="google_user",
            email="google.user@example.com",
            password="pass12345",
        )

    @override_settings(SOCIAL_AUTH_REQUESTS_TIMEOUT=3)
    @patch("api.v1.serializers.google_auth_serializers.requests.get")
    def test_google_login_accepts_access_token(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "email": self.user.email,
                "email_verified": True,
            },
        )

        response = self.client.post(
            reverse("mobile-auth-google"),
            {"access_token": "valid-google-access-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], self.user.email)
        mock_get.assert_called_once()

    def test_google_login_requires_token(self):
        response = self.client.post(reverse("mobile-auth-google"), {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    @override_settings(SOCIAL_AUTH_REQUESTS_TIMEOUT=3)
    @patch("api.v1.serializers.google_auth_serializers.requests.get")
    def test_google_login_creates_new_guest_account(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "email": "new.google.user@example.com",
                "email_verified": True,
                "given_name": "New",
                "family_name": "User",
                "sub": "google-user-123",
            },
        )

        response = self.client.post(
            reverse("mobile-auth-google"),
            {"access_token": "new-google-access-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user = User.objects.get(email="new.google.user@example.com")
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.profile.account_type, "guest")
        self.assertEqual(response.data["user"]["id"], user.id)
        self.assertTrue(
            UserSocialAuth.objects.filter(user=user, provider="google-oauth2", uid="google-user-123").exists()
        )

    @override_settings(SOCIAL_AUTH_REQUESTS_TIMEOUT=3)
    @patch("api.v1.serializers.google_auth_serializers.requests.get")
    def test_google_login_reuses_email_case_insensitively(self, mock_get):
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "email": self.user.email.upper(),
                "email_verified": True,
                "sub": "google-user-existing",
            },
        )

        response = self.client.post(
            reverse("mobile-auth-google"),
            {"access_token": "existing-google-access-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], self.user.id)
        self.assertEqual(User.objects.filter(email__iexact=self.user.email).count(), 1)

    @override_settings(SOCIAL_AUTH_REQUESTS_TIMEOUT=3)
    @patch("api.v1.serializers.google_auth_serializers.requests.get")
    def test_google_subject_resolves_the_previously_linked_user(self, mock_get):
        UserSocialAuth.objects.create(
            user=self.user,
            provider="google-oauth2",
            uid="stable-google-subject",
        )
        mock_get.return_value = Mock(
            status_code=200,
            json=lambda: {
                "email": "updated.google.email@example.com",
                "email_verified": True,
                "sub": "stable-google-subject",
            },
        )

        response = self.client.post(
            reverse("mobile-auth-google"),
            {"access_token": "linked-google-access-token"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["id"], self.user.id)
        self.assertFalse(User.objects.filter(email="updated.google.email@example.com").exists())


class MobileDeviceInstallationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("device_user", password="pass12345")
        self.other_user = User.objects.create_user("other_device_user", password="pass12345")
        self.installation_id = uuid4()
        self.payload = {
            "installation_id": str(self.installation_id),
            "push_token": "fcm-device-token-value-with-safe-length",
            "platform": "android",
            "app_version": "1.0.0",
            "notifications_enabled": True,
        }

    def test_registration_requires_authentication(self):
        response = self.client.post(reverse("mobile-device-installations-list"), self.payload, format="json")
        self.assertIn(response.status_code, {status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN})

    def test_registration_is_idempotent_for_user_and_installation(self):
        self.client.force_authenticate(self.user)
        first = self.client.post(reverse("mobile-device-installations-list"), self.payload, format="json")
        second = self.client.post(
            reverse("mobile-device-installations-list"),
            {**self.payload, "app_version": "1.0.1"},
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DeviceInstallation.objects.filter(user=self.user).count(), 1)
        self.assertEqual(DeviceInstallation.objects.get(user=self.user).app_version, "1.0.1")
        self.assertNotIn("push_token", second.data)

    def test_user_cannot_delete_another_users_installation(self):
        installation = DeviceInstallation.objects.create(
            user=self.other_user,
            installation_id=uuid4(),
            push_token="another-fcm-device-token-with-safe-length",
            platform="android",
        )
        self.client.force_authenticate(self.user)

        response = self.client.delete(reverse("mobile-device-installations-detail", args=[installation.id]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        installation.refresh_from_db()
        self.assertTrue(installation.active)


class MobileNotificationInboxTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("notification_user", password="pass12345")
        self.other_user = User.objects.create_user("other_notification_user", password="pass12345")
        self.notification = UserNotification.objects.create(
            user=self.user,
            event="loan_updated",
            record_id=42,
            title="Loan update",
            body="Your loan application was updated.",
        )
        UserNotification.objects.create(
            user=self.other_user,
            event="savings_updated",
            title="Savings update",
            body="Your savings account was updated.",
        )

    def test_inbox_is_private_and_supports_read_state(self):
        self.client.force_authenticate(self.user)

        listing = self.client.get(reverse("mobile-notifications-list"))
        unread = self.client.get(reverse("mobile-notifications-unread-count"))
        marked = self.client.post(reverse("mobile-notifications-mark-read", args=[self.notification.id]))
        after = self.client.get(reverse("mobile-notifications-unread-count"))

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listing.data["results"]), 1)
        self.assertEqual(listing.data["results"][0]["data"], {"event": "loan_updated", "record_id": 42})
        self.assertEqual(unread.data["count"], 1)
        self.assertEqual(marked.status_code, status.HTTP_200_OK)
        self.assertTrue(marked.data["is_read"])
        self.assertEqual(after.data["count"], 0)
