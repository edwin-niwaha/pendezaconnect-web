import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator

# Third-party Imports
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField


# sponsorship_type constants
class SponsorshipType:
    CHILD_FULL_SUPPORT = "Child full support"
    CHILD_CO_SUPPORT = "Child co-support"
    FAMILY_FULL_SUPPORT = "Family full support"
    FAMILY_CO_SUPPORT = "Family co-support"
    GENERAL_SUPPORT = "General support"


SPONSORSHIP_TYPE_CHOICES = (
    ("", "--choose sponsorship type--"),
    (SponsorshipType.CHILD_FULL_SUPPORT, "Child full support"),
    (SponsorshipType.CHILD_CO_SUPPORT, "Child co-support"),
    (SponsorshipType.FAMILY_FULL_SUPPORT, "Family full support"),
    (SponsorshipType.FAMILY_CO_SUPPORT, "Family co-support"),
    (SponsorshipType.GENERAL_SUPPORT, "General support"),
)

REAL_SUPPORT_PROGRAM_CODES = (
    "child_support",
    "child_co_support",
    "family_support",
    "family_co_support",
    "general_support",
    "staff_support",
)


def sponsorship_type_flags(sponsorship_type):
    return {
        "is_child_sponsor": sponsorship_type in (SponsorshipType.CHILD_FULL_SUPPORT, SponsorshipType.CHILD_CO_SUPPORT),
        "is_family_supporter": sponsorship_type
        in (SponsorshipType.FAMILY_FULL_SUPPORT, SponsorshipType.FAMILY_CO_SUPPORT),
        "is_general_donor": sponsorship_type == SponsorshipType.GENERAL_SUPPORT,
    }


class SponsorQuerySet(models.QuerySet):
    def with_report_related(self):
        return self.prefetch_related(
            "payments__program",
            "sponsored_children",
            "sponsored_staff",
        )

    def active(self):
        return self.filter(is_departed=False)

    def departed(self):
        return self.filter(is_departed=True)

    def child_sponsors(self):
        return self.filter(is_child_sponsor=True)

    def staff_sponsors(self):
        return self.filter(is_staff_sponsor=True)

    def family_supporters(self):
        return self.filter(is_family_supporter=True)

    def general_donors(self):
        return self.filter(is_general_donor=True)

    def one_time_donors(self):
        return self.filter(is_one_time_donor=True)

    def real_supporters(self):
        """
        Excludes one-time-only donors.

        Includes:
        - child sponsors
        - family supporters
        - general supporters
        - staff supporters
        """
        return self.filter(
            Q(is_child_sponsor=True) | Q(is_staff_sponsor=True) | Q(is_family_supporter=True) | Q(is_general_donor=True)
        ).distinct()

    def exclude_one_time_only_donors(self):
        return self.real_supporters()

    def real_sponsors_only(self):
        return self.real_supporters()

    def one_time_only_donors(self):
        return (
            self.one_time_donors()
            .exclude(
                Q(is_child_sponsor=True)
                | Q(is_staff_sponsor=True)
                | Q(is_family_supporter=True)
                | Q(is_general_donor=True)
            )
            .distinct()
        )

    def active_real_supporters(self):
        return self.active().real_supporters()

    def departed_real_supporters(self):
        return self.departed().real_supporters()


# =================================== SPONSOR MODEL ===================================
class Sponsor(models.Model):
    objects = SponsorQuerySet.as_manager()
    DEPARTURE_CHOICES = (
        ("Yes", "Yes"),
        ("No", "No"),
    )
    GENDER_CHOICES = (
        ("Male", "Male"),
        ("Female", "Female"),
    )

    first_name = models.CharField(max_length=50, null=True, verbose_name="First Name")
    last_name = models.CharField(max_length=50, null=True, verbose_name="Last Name")
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES, blank=False, verbose_name="Gender")
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date of Birth",
    )
    email = models.EmailField(verbose_name="Email")
    sponsorship_type = models.CharField(
        max_length=50,
        choices=SPONSORSHIP_TYPE_CHOICES,
        null=True,
        blank=True,
        verbose_name="Sponsorship Type",
    )
    expected_amt = models.DecimalField(_("Amount Expected(UgX)"), max_digits=10, decimal_places=2, default=0)
    job_title = models.CharField(max_length=100, null=True, blank=True, verbose_name="Job Title")
    region = models.CharField(max_length=100, null=True, blank=True, verbose_name="Region")
    town = models.CharField(max_length=100, null=True, blank=True, verbose_name="Town")
    origin = models.CharField(max_length=100, null=True, blank=True, verbose_name="Origin")
    business_telephone = PhoneNumberField(
        null=True,
        blank=True,
        default="+256999999999",
        verbose_name="Business Telephone",
    )
    mobile_telephone = PhoneNumberField(null=True, blank=True, default="+256999999999", verbose_name="Mobile Telephone")
    city = models.CharField(max_length=30, null=True, blank=True, verbose_name="City")
    start_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Start Date",
        validators=[
            MinValueValidator(limit_value=datetime.date(year=2013, month=1, day=1)),
            MaxValueValidator(limit_value=datetime.date.today),
        ],
    )
    first_street_address = models.CharField(max_length=100, null=True, blank=True, verbose_name="First Street Address")
    second_street_address = models.CharField(
        max_length=100, null=True, blank=True, verbose_name="Second Street Address"
    )
    zip_code = models.CharField(max_length=50, null=True, blank=True, verbose_name="ZIP Code or Box Number")
    is_departed = models.BooleanField(
        default=False,
        verbose_name="Departed?",
    )
    is_child_sponsor = models.BooleanField(default=False)
    is_staff_sponsor = models.BooleanField(default=False)
    is_family_supporter = models.BooleanField(default=False)
    is_general_donor = models.BooleanField(default=False)
    is_one_time_donor = models.BooleanField(default=False)
    comment = models.CharField(max_length=100, null=True, blank=True, verbose_name="Comment")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = True
        db_table = "sponsor_details"

    def clean(self):
        # Validate that date_of_birth is not in the future
        if self.date_of_birth and self.date_of_birth > datetime.date.today():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})

        # Call the parent clean method to ensure other validations still work
        super().clean()

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    def save(self, *args, **kwargs):
        for field, value in sponsorship_type_flags(self.sponsorship_type).items():
            if value:
                setattr(self, field, True)
        super().save(*args, **kwargs)

    @property
    def prefixed_id(self):
        if self.pk < 10:
            return f"PS00{self.pk}"
        elif self.pk < 100:
            return f"PS0{self.pk}"
        else:
            return f"PS{self.pk}"


# =================================== DONOR MODEL ===================================
class Donor(models.Model):
    full_name = models.CharField(_("Full Name"), max_length=255)
    email = models.EmailField(_("Email"), null=True, blank=True)
    phone = models.CharField(_("Phone"), max_length=20, null=True, blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    def __str__(self):
        return self.full_name


# =================================== SPONSOR DEPARTURE MODEL ===================================
class SponsorDeparture(models.Model):
    sponsor = models.ForeignKey(
        Sponsor,  # Direct reference to the Sponsor model
        on_delete=models.CASCADE,
        verbose_name="Sponsor Information",
        related_name="departures",
    )
    departure_date = models.DateField(verbose_name="Departure Date", null=True, blank=True)
    departure_reason = models.TextField(verbose_name="Reason for Departure")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        verbose_name = "Sponsor Departure"
        verbose_name_plural = "Sponsor Departures"


class SponsorFeedbackQuerySet(models.QuerySet):
    def unread(self):
        return self.filter(status=SponsorFeedback.Status.NEW)

    def with_related(self):
        return self.select_related("sponsor", "submitted_by")


class SponsorFeedback(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        REVIEWED = "reviewed", "Reviewed"
        RESOLVED = "resolved", "Resolved"

    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sponsor_feedback_submissions",
    )
    subject = models.CharField(max_length=150)
    message = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    admin_notes = models.TextField(blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    email_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SponsorFeedbackQuerySet.as_manager()

    class Meta:
        db_table = "sponsor_feedback"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["sponsor", "created_at"]),
        ]

    def __str__(self):
        return f"{self.sponsor} - {self.subject}"
