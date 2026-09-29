"""Client workbook processing runs outside the HTTP worker."""

import logging
from dataclasses import asdict
from io import BytesIO
from zipfile import ZipFile

from celery import shared_task
from django.utils import timezone

from .importing import import_clients
from .models import ClientImportJob

logger = logging.getLogger(__name__)


def enqueue_client_import(job_id):
    try:
        run_client_import.apply_async(args=[job_id], retry=False)
    except Exception:
        logger.exception("Could not enqueue client import %s", job_id)
        ClientImportJob.objects.filter(pk=job_id, status="queued").update(
            status="failed", workbook=None, updated_at=timezone.now(),
            error="Could not queue the import. Check the background worker connection, then upload again.",
        )


@shared_task(ignore_result=True)
def run_client_import(job_id):
    # Duplicate message deliveries must not run the same upload twice.
    if not ClientImportJob.objects.filter(pk=job_id, status="queued").update(
        status="processing", updated_at=timezone.now()
    ):
        return
    result = {}

    def progress(processed, current):
        nonlocal result
        result = asdict(current)
        ClientImportJob.objects.filter(pk=job_id).update(
            processed=processed, result=result, updated_at=timezone.now()
        )

    try:
        job = ClientImportJob.objects.get(pk=job_id)
        source = BytesIO(bytes(job.workbook))
        # A small compressed upload can otherwise expand beyond worker memory.
        with ZipFile(source) as archive:
            if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                raise ValueError("Workbook is too large when expanded. Split it into smaller files.")
        source.seek(0)
        result = asdict(import_clients(source, report=True, progress=progress))
        ClientImportJob.objects.filter(pk=job_id).update(
            status="completed", processed=result["processed"], result=result,
            workbook=None, updated_at=timezone.now(),
        )
    except Exception as exc:
        logger.exception("Client import %s failed", job_id)
        message = (
            str(exc) if isinstance(exc, ValueError)
            else "Import stopped. Some rows may already be saved. Check the worker logs and workbook before retrying."
        )
        ClientImportJob.objects.filter(pk=job_id).update(
            status="failed", workbook=None, result=result, updated_at=timezone.now(),
            error=message,
        )
