from unittest.mock import patch

from cloudinary import CloudinaryResource
from cloudinary.exceptions import Error as CloudinaryError
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .forms import PolicyForm
from .models import Policy, Profile


def pdf_upload(name="policy.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF", content_type="application/pdf")


def stored_document():
    return CloudinaryResource("policies/example.pdf", resource_type="raw", type="upload", version=1)


class PolicyFormTests(SimpleTestCase):
    def test_pdf_is_validated_without_uploading_to_cloudinary(self):
        with patch("cloudinary.uploader.upload_image") as upload:
            form = PolicyForm({"title": "Policy"}, {"upload": pdf_upload("policy.PDF")})
            self.assertTrue(form.is_valid(), form.errors)
        upload.assert_not_called()

    def test_rejects_non_pdf_and_oversized_files(self):
        invalid_files = [pdf_upload("policy.docx"), pdf_upload()]
        invalid_files[1].size = 10 * 1024 * 1024 + 1
        for file in invalid_files:
            with self.subTest(name=file.name, size=file.size):
                form = PolicyForm({"title": "Policy"}, {"upload": file})
                self.assertFalse(form.is_valid())
                self.assertIn("upload", form.errors)

    def test_edit_without_replacement_keeps_stored_document(self):
        document = stored_document()
        form = PolicyForm({"title": "Updated policy"}, instance=Policy(title="Policy", upload=document))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIs(form.cleaned_data["upload"], document)


class PolicyUploadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="policy-manager")
        Profile.objects.create(user=cls.user, account_type="staff", staff_role="manager", role="manager")

    def setUp(self):
        self.client.force_login(self.user)

    @patch("cloudinary.uploader.upload_resource")
    def test_create_uploads_raw_document_and_redirects(self, upload):
        upload.return_value = stored_document()
        response = self.client.post(reverse("upload_policy"), {"title": "Policy", "upload": pdf_upload()})
        self.assertRedirects(response, reverse("policy_list"))
        self.assertEqual(Policy.objects.count(), 1)
        self.assertEqual(Policy.objects.get().upload.resource_type, "raw")
        upload.assert_called_once()
        self.assertEqual(upload.call_args.kwargs["resource_type"], "raw")

    @patch("cloudinary.uploader.upload_resource")
    def test_invalid_upload_does_not_reach_storage(self, upload):
        response = self.client.post(reverse("upload_policy"), {"title": "Policy", "upload": pdf_upload("bad.txt")})
        self.assertEqual(response.status_code, 200)
        self.assertIn("upload", response.context["form"].errors)
        self.assertFalse(Policy.objects.exists())
        upload.assert_not_called()

    @patch("cloudinary.uploader.upload_resource")
    def test_storage_failure_shows_form_error_without_creating_policy(self, upload):
        upload.side_effect = CloudinaryError("Storage service unavailable")
        with self.assertLogs("apps.users.views", level="ERROR"):
            response = self.client.post(reverse("upload_policy"), {"title": "Policy", "upload": pdf_upload()})
        self.assertEqual(response.status_code, 200)
        self.assertIn("upload", response.context["form"].errors)
        self.assertEqual(response.context["form"]["title"].value(), "Policy")
        self.assertNotContains(response, "Storage service unavailable")
        self.assertFalse(Policy.objects.exists())

    @patch("cloudinary.uploader.upload_resource")
    def test_update_without_new_file_keeps_document(self, upload):
        policy = Policy.objects.create(title="Policy", upload=stored_document())
        response = self.client.post(reverse("update_policy", args=[policy.pk]), {"title": "Updated policy"})
        self.assertRedirects(response, reverse("policy_list"))
        policy.refresh_from_db()
        self.assertEqual(policy.title, "Updated policy")
        self.assertEqual(policy.upload.public_id, "policies/example")
        upload.assert_not_called()

    @patch("cloudinary.uploader.upload_resource")
    def test_failed_replacement_preserves_existing_policy(self, upload):
        policy = Policy.objects.create(title="Original policy", upload=stored_document())
        original_document = policy.upload.get_prep_value()
        upload.side_effect = CloudinaryError("Storage service unavailable")
        with self.assertLogs("apps.users.views", level="ERROR"):
            response = self.client.post(
                reverse("update_policy", args=[policy.pk]),
                {"title": "Changed policy", "upload": pdf_upload()},
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("upload", response.context["form"].errors)
        policy.refresh_from_db()
        self.assertEqual(policy.title, "Original policy")
        self.assertEqual(policy.upload.get_prep_value(), original_document)
