from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from django.test.client import RequestFactory
from django.urls import reverse

from apps.client.models import Client
from apps.sponsor.models import Sponsor

from .forms import LoginForm
from .models import Profile
from .pipeline import require_google_login_token
from .views import CustomLoginView


class LoginFormTests(TestCase):
    def test_login_accepts_email_address_as_username(self):
        User.objects.create_user(
            username="client-user",
            email="client@example.com",
            password="pass12345",
        )

        form = LoginForm(
            request=None,
            data={
                "username": "client@example.com",
                "password": "pass12345",
            },
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.get_user().username, "client-user")


class PublicLandingTests(TestCase):
    def test_home_page_hides_client_portal_for_anonymous_visitors(self):
        response = self.client.get(reverse("users-home"))

        self.assertNotContains(response, "Client Portal")
        self.assertNotContains(response, reverse("client_savings_dashboard"))

    def test_home_page_shows_client_portal_for_authenticated_visitors(self):
        client_record = Client.objects.create(
            full_name="Client Member",
            email="client@example.com",
            reg_number="C101",
        )
        user = User.objects.create_user(username="member", password="pass12345")
        Profile.objects.update_or_create(
            user=user,
            defaults={
                "account_type": "client",
                "role": "client",
                "bio": "",
                "client": client_record,
            },
        )

        self.client.force_login(user)
        response = self.client.get(reverse("users-home"))

        self.assertContains(response, "Client Portal")
        self.assertContains(response, reverse("client_savings_dashboard"))

    def test_login_page_offers_google_and_password_login(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, "Continue with Google")
        self.assertContains(response, "Email or username")

    def test_google_login_continues_without_email_token(self):
        user = User.objects.create_user(
            username="google-member",
            email="google@example.com",
        )
        request = RequestFactory().get("/oauth/complete/google-oauth2/")
        request.session = SessionStore()
        request._messages = FallbackStorage(request)

        class Strategy:
            def __init__(self, request):
                self.request = request

            def session_get(self, key):
                return None

        class Backend:
            name = "google-oauth2"

        response = require_google_login_token(Strategy(request), Backend(), user=user)

        self.assertIsNone(response)
        self.assertTrue(Profile.objects.filter(user=user).exists())
        self.assertNotIn("_auth_user_id", request.session)

    def test_email_login_signs_in_directly(self):
        user = User.objects.create_user(
            username="member",
            email="member@example.com",
            password="pass12345",
        )

        response = self.client.post(
            reverse("login"),
            {"username": "member@example.com", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("users-home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_linked_client_login_redirects_to_landing_page(self):
        client_record = Client.objects.create(
            full_name="Client Member",
            email="member@example.com",
            reg_number="C100",
        )
        user = User.objects.create_user(
            username="member",
            email="member@example.com",
            password="pass12345",
        )
        Profile.objects.update_or_create(
            user=user,
            defaults={"role": "guest", "bio": "", "client": client_record},
        )

        response = self.client.post(
            reverse("login"),
            {"username": "member@example.com", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("users-home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_redirects_all_account_types_to_landing_page(self):
        login_view = CustomLoginView()
        staff = User.objects.create_user(username="staff-member", password="pass12345")
        client_user = User.objects.create_user(
            username="client-member",
            email="client2@example.com",
            password="pass12345",
        )
        sponsor_user = User.objects.create_user(
            username="sponsor-member",
            email="sponsor@example.com",
            password="pass12345",
        )
        client_record = Client.objects.create(
            full_name="Client Two",
            email="client2@example.com",
            reg_number="C102",
        )
        sponsor_record = Sponsor.objects.create(
            first_name="Sponsor",
            last_name="Member",
            gender="Male",
            email="sponsor@example.com",
        )
        Profile.objects.update_or_create(
            user=staff,
            defaults={
                "account_type": "staff",
                "staff_role": "boo",
                "role": "boo",
                "bio": "",
            },
        )
        Profile.objects.update_or_create(
            user=client_user,
            defaults={
                "account_type": "client",
                "role": "client",
                "client": client_record,
                "bio": "",
            },
        )
        Profile.objects.update_or_create(
            user=sponsor_user,
            defaults={
                "account_type": "sponsor",
                "role": "sponsor",
                "sponsor": sponsor_record,
                "bio": "",
            },
        )

        self.assertEqual(
            login_view.get_success_url_for_user(staff), reverse("users-home")
        )
        self.assertEqual(
            login_view.get_success_url_for_user(client_user),
            reverse("users-home"),
        )
        self.assertEqual(
            login_view.get_success_url_for_user(sponsor_user),
            reverse("users-home"),
        )
