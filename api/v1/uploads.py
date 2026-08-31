from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
DOCUMENT_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def validate_image_upload(upload):
    if getattr(upload, "size", 0) > MAX_IMAGE_BYTES:
        raise serializers.ValidationError({"picture": ["Image files must be 8 MB or smaller."]})
    try:
        serializers.ImageField().run_validation(upload)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"picture": exc.messages}) from exc
    if hasattr(upload, "seek"):
        upload.seek(0)
    return upload


def validate_document_upload(upload, field_name="file"):
    extension = Path(getattr(upload, "name", "")).suffix.lower()
    content_type = str(getattr(upload, "content_type", "")).lower()
    if extension not in DOCUMENT_EXTENSIONS or content_type not in DOCUMENT_CONTENT_TYPES:
        raise serializers.ValidationError({field_name: ["Upload a JPG, PNG, or PDF document."]})
    if getattr(upload, "size", 0) > MAX_DOCUMENT_BYTES:
        raise serializers.ValidationError({field_name: ["Document files must be 10 MB or smaller."]})
    if content_type.startswith("image/"):
        serializers.ImageField().run_validation(upload)
    elif hasattr(upload, "read"):
        signature = upload.read(5)
        if signature != b"%PDF-":
            raise serializers.ValidationError({field_name: ["The uploaded PDF is invalid."]})
    if hasattr(upload, "seek"):
        upload.seek(0)
    return upload
