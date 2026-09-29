from io import BytesIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from apps.client.importing import import_clients
from apps.client.models import Client, ClientImportJob
from apps.client.tasks import enqueue_client_import, run_client_import
from apps.users.models import Profile

from .test_profile import ClientProfileTests


class ClientImportJobTests(TestCase):
    workbook = ClientProfileTests.workbook

    def setUp(self):
        self.user = User.objects.create_user(username="import-admin")
        Profile.objects.create(user=self.user, role="administrator")
        self.client.force_login(self.user)

    def job(self, rows):
        source = self.workbook(["reg_number", "full_name"], rows)
        return ClientImportJob.objects.create(user=self.user, filename="clients.xlsx", workbook=source.getvalue())

    def test_worker_imports_valid_rows_once_and_removes_payload(self):
        job = self.job([["NEW", "New Client"], ["", "Invalid Client"]])
        run_client_import(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.result["created"], 1)
        self.assertEqual(len(job.result["errors"]), 1)
        self.assertEqual(job.processed, 2)
        self.assertIsNone(job.workbook)
        with patch("apps.client.tasks.import_clients") as importer:
            run_client_import(job.pk)
        importer.assert_not_called()

    def test_queue_failure_is_visible_and_does_not_import(self):
        job = self.job([["NEW", "New Client"]])
        with (
            patch("apps.client.tasks.run_client_import.apply_async", side_effect=ConnectionError),
            self.assertLogs("apps.client.tasks", level="ERROR"),
        ):
            enqueue_client_import(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.workbook)
        self.assertIn("Could not queue", job.error)
        self.assertFalse(Client.objects.exists())

    def test_invalid_workbook_fails_without_exposing_exception(self):
        job = ClientImportJob.objects.create(user=self.user, filename="broken.xlsx", workbook=b"invalid file")
        with self.assertLogs("apps.client.tasks", level="ERROR"):
            run_client_import(job.pk)
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIsNone(job.workbook)
        self.assertFalse(Client.objects.exists())

    def test_status_is_private_and_never_cached(self):
        job = self.job([["NEW", "New Client"]])
        url = reverse("client_import_status", args=[job.pk])
        response = self.client.get(url, {"format": "json"})
        self.assertEqual(response.json(), {"status": "queued", "processed": 0})
        self.assertIn("no-store", response["Cache-Control"])
        other = User.objects.create_user(username="other-admin")
        Profile.objects.create(user=other, role="administrator")
        self.client.force_login(other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_duplicate_rows_near_end_are_detected_before_any_writes(self):
        source = self.workbook(["reg_number", "full_name"], [[" DUP ", "One"], ["dup", "Two"]])
        result = import_clients(source, report=True)
        self.assertEqual(len(result.errors), 2)
        self.assertFalse(Client.objects.exists())

    def test_progress_callback_and_streaming_preserve_counts(self):
        job = self.job([[f"REG-{number}", f"Client {number}"] for number in range(101)])
        progress = []
        result = import_clients(
            BytesIO(bytes(job.workbook)), report=True,
            progress=lambda processed, result: progress.append((processed, result.created)),
        )
        self.assertEqual(progress, [(100, 100)])
        self.assertEqual((result.processed, result.created, result.errors), (101, 101, []))

    def test_oversized_upload_is_rejected_before_queueing(self):
        source = BytesIO(b"x" * (10 * 1024 * 1024 + 1))
        source.name = "too-large.xlsx"
        response = self.client.post(reverse("import_client_data"), {"excel_file": source})
        self.assertContains(response, "smaller than 10 MB")
        self.assertFalse(ClientImportJob.objects.exists())
