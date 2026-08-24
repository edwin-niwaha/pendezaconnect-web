import os
from io import BytesIO

from cloudinary.models import CloudinaryField
from cloudinary.uploader import upload
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db import models
from PIL import Image

from apps.client.models import Client
from apps.sponsor.models import Sponsor

# =================================== Profile Model  ===================================


class Profile(models.Model):
    ACCOUNT_TYPE_CHOICES = (
        ("guest", "Guest / New User"),
        ("client", "Client"),
        ("sponsor", "Sponsor"),
        ("staff", "Staff"),
    )
    STAFF_ROLE_CHOICES = (
        ("", "No staff role"),
        ("administrator", "Administrator"),
        ("manager", "Manager"),
        ("staff", "General Staff"),
        ("boo", "Business Operations Officer"),
        ("hof", "Head of Finance"),
        ("accountant", "Accountant"),
        ("ed", "Executive Director"),
    )
    ROLE_CHOICES = (
        ("administrator", "Administrator"),
        ("manager", "Manager"),
        ("staff", "Staff"),
        ("guest", "Guest"),
        ("client", "Client"),
        ("sponsor", "Sponsor"),
        ("boo", "Business Operations Officer"),
        ("hof", "Head of Finance"),
        ("accountant", "Accountant"),
        ("ed", "Executive Director"),
    )

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    client = models.OneToOneField(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
        verbose_name="Linked Client Account",
    )
    sponsor = models.OneToOneField(
        Sponsor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="user_profile",
        verbose_name="Linked Sponsor Account",
    )
    account_type = models.CharField(
        max_length=20,
        choices=ACCOUNT_TYPE_CHOICES,
        default="guest",
        help_text="Primary workspace this user should enter after login.",
    )
    staff_role = models.CharField(
        max_length=20,
        choices=STAFF_ROLE_CHOICES,
        blank=True,
        default="",
        help_text="Only used when account type is Staff.",
    )
    role = models.CharField(max_length=15, choices=ROLE_CHOICES, default="guest")
    avatar = CloudinaryField("avatar", default="default.jpg")
    bio = models.TextField()

    STAFF_LEGACY_ROLES = {
        "administrator",
        "manager",
        "staff",
        "boo",
        "hof",
        "accountant",
        "ed",
    }

    def __str__(self):
        return self.user.username

    @property
    def resolved_account_type(self):
        if self.account_type and self.account_type != "guest":
            return self.account_type
        if self.role in self.STAFF_LEGACY_ROLES:
            return "staff"
        if self.client_id:
            return "client"
        if self.sponsor_id or self.role == "sponsor":
            return "sponsor"
        return "guest"

    @property
    def resolved_staff_role(self):
        if self.staff_role:
            return self.staff_role
        if self.role in self.STAFF_LEGACY_ROLES:
            return self.role
        return ""

    @property
    def is_staff_account(self):
        return self.resolved_account_type == "staff"

    @property
    def is_client_account(self):
        return self.resolved_account_type == "client"

    @property
    def is_sponsor_account(self):
        return self.resolved_account_type == "sponsor"

    def save(self, *args, **kwargs):
        if self.client_id:
            self.account_type = "client"
        elif self.sponsor_id:
            self.account_type = "sponsor"
        elif self.staff_role or self.role in self.STAFF_LEGACY_ROLES:
            self.account_type = "staff"

        if self.account_type == "staff" and not self.staff_role:
            self.staff_role = (
                self.role if self.role in self.STAFF_LEGACY_ROLES else "staff"
            )
        elif self.account_type != "staff":
            self.staff_role = ""

        if self.account_type in {"client", "sponsor"}:
            self.role = self.account_type
        elif self.account_type == "staff" and self.staff_role:
            self.role = self.staff_role

        if isinstance(self.avatar, InMemoryUploadedFile):
            # If a new file is being uploaded
            with Image.open(self.avatar) as img:
                # Resize if necessary
                if img.height > 100 or img.width > 100:
                    output = BytesIO()
                    try:
                        img.thumbnail((100, 100))
                        img.save(output, format=img.format)
                        output.seek(0)

                        # Upload resized image to Cloudinary
                        upload_result = upload(output, folder="profile_images")
                        self.avatar = upload_result["public_id"]
                    finally:
                        output.close()

        super().save(*args, **kwargs)


# =================================== Contact Model  ===================================
class Contact(models.Model):
    name = models.CharField(max_length=100, verbose_name="Your Name")
    email = models.EmailField(verbose_name="Your Email")
    message = models.TextField(verbose_name="Message")
    is_valid = models.BooleanField(default=False, verbose_name="Valid?")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "User Feedback"
        db_table = "user_feedback"

    def __str__(self):
        return f"Feedback from {self.name} ({self.email})"


class DeviceInstallation(models.Model):
    PLATFORM_ANDROID = "android"
    PLATFORM_IOS = "ios"
    PLATFORM_CHOICES = (
        (PLATFORM_ANDROID, "Android"),
        (PLATFORM_IOS, "iOS"),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_installations",
    )
    installation_id = models.UUIDField()
    push_token = models.CharField(max_length=512)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    app_version = models.CharField(max_length=32, blank=True)
    notifications_enabled = models.BooleanField(default=True)
    active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "installation_id"),
                name="unique_user_device_installation",
            )
        ]
        indexes = [
            models.Index(fields=("user", "active"), name="users_devic_user_id_eeac14_idx"),
            models.Index(fields=("push_token",), name="users_devic_push_to_f8b98d_idx"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.platform}:{self.installation_id}"


class UserNotification(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    event = models.CharField(max_length=50)
    record_id = models.PositiveBigIntegerField(null=True, blank=True)
    title = models.CharField(max_length=160)
    body = models.TextField(max_length=500)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=("user", "read_at"), name="users_notif_user_read_idx"),
            models.Index(fields=("user", "created_at"), name="users_notif_user_date_idx"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.event}:{self.id}"


# =================================== Policy Model  ===================================
class Policy(models.Model):
    title = models.CharField(max_length=50)
    # upload = models.FileField(upload_to="policies/", blank=True, null=True)
    upload = CloudinaryField("policies", resource_type="raw", null=True, blank=True)

    is_valid = models.BooleanField(
        default=False,
        verbose_name="Valid?",
    )
    date_reviewed = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def document_url(self):
        if not self.upload:
            return ""

        return self.upload.url

    @property
    def needs_document_reupload(self):
        return bool(
            self.upload
            and "/image/upload/" in self.upload.url
            and self.upload.url.lower().endswith(".pdf")
        )

    def __str__(self):
        return self.title


# =================================== PolicyRead Model ===================================
class PolicyRead(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    policy = models.ForeignKey(Policy, on_delete=models.CASCADE)
    read_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")

    class Meta:
        unique_together = ("user", "policy")

    def __str__(self):
        return f"{self.user.username} read {self.policy.title}"


# =================================== Ebook Model  ===================================
class Ebook(models.Model):
    title = models.CharField(max_length=200)
    author = models.CharField(max_length=200)
    ebook_file = CloudinaryField(
        "ebook_file", resource_type="auto"
    )  # Handles PDF uploads
    upload_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def document_url(self):
        if not self.ebook_file:
            return ""
        return self.ebook_file.url

    def __str__(self):
        return self.title


# =================================== Document Uploads  ===================================
# Custom validator function
def validate_file_extension(value):
    ext = os.path.splitext(value.name)[1]
    valid_extensions = [".pdf", ".xls", ".xlsx"]
    if ext.lower() not in valid_extensions:
        raise ValidationError(
            "Unsupported file extension. Only PDF and Excel files are allowed."
        )


class DocumentUpload(models.Model):
    title = models.CharField(max_length=50, verbose_name="Document Title")
    # file = models.FileField(
    #     upload_to="default_uploads/", validators=[validate_file_extension]
    # )
    file = CloudinaryField(
        "documents",
        resource_type="auto",  # auto detects the resource type (image, pdf, etc.)
        validators=[validate_file_extension],  # Apply the file extension validator
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def document_url(self):
        if not self.file:
            return ""
        return self.file.url

    class Meta:
        verbose_name = "Document Upload"
        verbose_name_plural = "Document Uploads"
        ordering = ["-created_at"]
        db_table = "document_uploads"

    def __str__(self):
        return self.title
