from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.client.models import Client, ClientRegistrationDraft
from apps.users.models import Profile


class RegistrationDraftTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="draft-staff")
        Profile.objects.create(user=self.user, role="manager")
        self.client.force_login(self.user)
        self.client.get(reverse("register_client"))
        self.draft = ClientRegistrationDraft.objects.get(user=self.user)

    def save(self, **data):
        return self.client.post(
            reverse("save_registration_draft"),
            {
                "draft_id": self.draft.pk,
                "revision": self.draft.revision,
                "step": 2,
                **data,
            },
        )

    def test_partial_draft_is_restored_without_creating_client(self):
        response = self.save(full_name="Incomplete client", branch="Central")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Client.objects.count(), 0)
        page = self.client.get(reverse("register_client"))
        self.assertContains(page, 'value="Incomplete client"')
        self.assertContains(page, 'data-draft-step="2"')
        self.assertContains(page, "Saved draft restored")

    def test_stale_save_and_other_user_cannot_overwrite(self):
        self.assertEqual(self.save(full_name="First").status_code, 200)
        self.assertEqual(self.save(full_name="Stale").status_code, 409)
        other = User.objects.create_user(username="other-staff")
        Profile.objects.create(user=other, role="manager")
        self.client.force_login(other)
        self.assertEqual(self.save(full_name="Other").status_code, 409)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.data["full_name"], "First")

    def test_final_registration_clears_draft_and_repeated_post_does_not_duplicate(self):
        self.save(full_name="Ready Client", client_type="individual")
        data = {"draft_id": self.draft.pk, "full_name": "Ready Client", "client_type": "individual"}
        self.assertEqual(self.client.post(reverse("register_client"), data).status_code, 302)
        self.assertFalse(ClientRegistrationDraft.objects.filter(pk=self.draft.pk).exists())
        self.client.post(reverse("register_client"), data)
        self.assertEqual(Client.objects.count(), 1)
        self.assertEqual(self.save(full_name="Delayed autosave").status_code, 409)

    def test_invalid_final_submission_keeps_draft(self):
        self.save(full_name="Saved Client")
        response = self.client.post(reverse("register_client"), {"draft_id": self.draft.pk, "full_name": "X"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ClientRegistrationDraft.objects.filter(pk=self.draft.pk).exists())
        self.assertEqual(Client.objects.count(), 0)

    def test_photo_saved_restored_and_removed(self):
        output = BytesIO()
        Image.new("RGB", (20, 20), "green").save(output, format="PNG")
        photo = SimpleUploadedFile("sample.png", output.getvalue(), content_type="image/png")
        self.assertEqual(self.save(picture=photo).status_code, 200)
        self.draft.refresh_from_db()
        self.assertTrue(self.draft.photo)
        self.assertContains(self.client.get(reverse("register_client")), "data:image/jpeg;base64,")
        self.assertEqual(self.save(remove_picture="1").status_code, 200)
        self.draft.refresh_from_db()
        self.assertIsNone(self.draft.photo)

    def test_csrf_required(self):
        self.client.handler.enforce_csrf_checks = True
        self.assertEqual(self.save(full_name="Unsafe").status_code, 403)
