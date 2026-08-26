"""Shared validation and resizing for client and child profile photos."""

from io import BytesIO
from pathlib import Path

from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image, ImageOps

MAX_PROFILE_PHOTO_BYTES = 8 * 1024 * 1024
MAX_PROFILE_PHOTO_DIMENSION = 1920


def normalize_profile_photo(upload):
    if not upload:
        return upload
    if getattr(upload, "size", 0) > MAX_PROFILE_PHOTO_BYTES:
        raise ValueError("Photo must be 8 MB or smaller.")
    try:
        upload.seek(0)
        with Image.open(upload) as source:
            source.verify()
        upload.seek(0)
        with Image.open(upload) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode not in ("RGB", "L"):
                background = Image.new("RGB", image.size, "white")
                mask = image.getchannel("A") if "A" in image.getbands() else None
                background.paste(image, mask=mask)
                image = background
            elif image.mode == "L":
                image = image.convert("RGB")
            image.thumbnail((MAX_PROFILE_PHOTO_DIMENSION,) * 2, Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(
                output,
                format="JPEG",
                quality=90,
                optimize=True,
                progressive=True,
            )
    except (OSError, ValueError) as exc:
        raise ValueError("Choose a valid JPG, PNG, or WebP photo.") from exc
    output.seek(0)
    stem = Path(getattr(upload, "name", "profile-photo")).stem or "profile-photo"
    return InMemoryUploadedFile(
        output,
        getattr(upload, "field_name", "picture"),
        f"{stem}.jpg",
        "image/jpeg",
        output.getbuffer().nbytes,
        None,
    )
