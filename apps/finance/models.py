# Standard Library Imports
from datetime import date

from django.core.validators import MaxValueValidator, MinValueValidator

# Third-party Imports
from django.db import models
from django.utils.translation import gettext_lazy as _

# Local App Imports
from apps.child.models import Child
from apps.sponsor.models import Donor, Sponsor
from apps.staff.models import Staff

# =================================== CHILD-SPONSOR PAYMENT MODEL ===================================
# Define choices for months
MONTH_CHOICES = (
    ("", "--select month--"),
    ("January", "January"),
    ("February", "February"),
    ("March", "March"),
    ("April", "April"),
    ("May", "May"),
    ("June", "June"),
    ("July", "July"),
    ("August", "August"),
    ("September", "September"),
    ("October", "October"),
    ("November", "November"),
    ("December", "December"),
)


class ChildPayments(models.Model):
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name="child_payments",
        verbose_name=_("Sponsor"),
    )

    child = models.ForeignKey(
        Child,
        on_delete=models.CASCADE,
        related_name="child_payments_received",
        verbose_name=_("Child"),
        null=True,
        blank=True,
    )
    payment_date = models.DateField(
        _("Date of payment"),
        validators=[
            MinValueValidator(limit_value=date(2018, 1, 1)),
            MaxValueValidator(limit_value=date.today),
        ],
    )
    month = models.CharField(_("Month of payment"), max_length=20, choices=MONTH_CHOICES)
    payment_year = models.IntegerField(_("Year of payment"), default=2018)
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2, default=0)
    # amount = models.IntegerField(_('Amount'), default=0)
    is_valid = models.BooleanField(
        default=False,
        verbose_name="Valid?",
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        db_table = "child_payments"
        verbose_name = _("Child Payment")
        verbose_name_plural = _("Child Payments")

    def __str__(self):
        return f"{self.sponsor} - {self.child} - {self.month}"


class SupportProgram(models.Model):
    CHILD_SUPPORT = "child_support"
    CHILD_CO_SUPPORT = "child_co_support"
    FAMILY_SUPPORT = "family_support"
    FAMILY_CO_SUPPORT = "family_co_support"
    GENERAL_SUPPORT = "general_support"
    STAFF_SUPPORT = "staff_support"
    ONE_TIME_DONATION = "one_time_donation"

    PROGRAM_CHOICES = (
        (CHILD_SUPPORT, "Child Support"),
        (CHILD_CO_SUPPORT, "Child Co-support"),
        (FAMILY_SUPPORT, "Family Support"),
        (FAMILY_CO_SUPPORT, "Family Co-support"),
        (GENERAL_SUPPORT, "General Support"),
        (STAFF_SUPPORT, "Staff Support"),
        (ONE_TIME_DONATION, "One-time Donation"),
    )
    REAL_SUPPORT_CODES = (
        CHILD_SUPPORT,
        CHILD_CO_SUPPORT,
        FAMILY_SUPPORT,
        FAMILY_CO_SUPPORT,
        GENERAL_SUPPORT,
        STAFF_SUPPORT,
    )

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, choices=PROGRAM_CHOICES, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "support_programs"
        ordering = ["name"]

    def __str__(self):
        return self.name


class PaymentQuerySet(models.QuerySet):
    def with_related(self):
        return self.select_related("sponsor", "program", "child", "staff")

    def for_real_support_programs(self):
        return self.filter(program__code__in=SupportProgram.REAL_SUPPORT_CODES)

    def real_support_payments(self):
        return self.for_real_support_programs()

    def one_time_donations(self):
        return self.filter(program__code=SupportProgram.ONE_TIME_DONATION)

    def one_time_only(self):
        sponsor_ids = (
            Payment.objects.for_real_support_programs().filter(sponsor=models.OuterRef("sponsor")).values("sponsor")
        )
        return self.one_time_donations().exclude(models.Exists(sponsor_ids))


class Payment(models.Model):
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    program = models.ForeignKey(
        SupportProgram,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    child = models.ForeignKey(
        Child,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unified_payments",
    )
    staff = models.ForeignKey(
        Staff,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unified_payments",
    )

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_date = models.DateField()
    reference = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(null=True, blank=True)

    source_model = models.CharField(max_length=100, null=True, blank=True)
    source_id = models.PositiveIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    objects = PaymentQuerySet.as_manager()

    class Meta:
        db_table = "payments"
        ordering = ["-payment_date", "-id"]
        indexes = [
            models.Index(fields=["sponsor", "program"]),
            models.Index(fields=["payment_date"]),
            models.Index(fields=["source_model", "source_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["source_model", "source_id"],
                name="unique_legacy_payment_source",
            )
        ]

    def __str__(self):
        return f"{self.sponsor} - {self.program} - {self.amount}"


# =================================== DONOR PAYMENT MODEL ===================================


class DonorPayment(models.Model):
    donor = models.ForeignKey(
        Donor,
        on_delete=models.CASCADE,
        related_name="donor_payments",
        verbose_name=_("Donor"),
    )
    payment_date = models.DateField(
        _("Date of payment"),
        validators=[
            MinValueValidator(limit_value=date(2018, 1, 1)),
            MaxValueValidator(limit_value=date.today),
        ],
    )
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        db_table = "donor_payments"
        verbose_name = _("Donor Payment")
        verbose_name_plural = _("Donor Payments")

    def __str__(self):
        return f"{self.donor} - {self.month} {self.payment_year}"


# =================================== STAFF-SPONSOR PAYMENT MODEL ===================================
class StaffPayments(models.Model):
    sponsor = models.ForeignKey(
        Sponsor,
        on_delete=models.CASCADE,
        related_name="staff_payments",
        verbose_name=_("Sponsor"),
    )
    staff = models.ForeignKey(
        Staff,
        on_delete=models.CASCADE,
        related_name="staff_payments_received",
        verbose_name=_("Staff"),
    )
    payment_date = models.DateField(
        _("Date of payment"),
        validators=[
            MinValueValidator(limit_value=date(2018, 1, 1)),
            MaxValueValidator(limit_value=date.today),
        ],
    )
    month = models.CharField(_("Month of payment"), max_length=20, choices=MONTH_CHOICES)
    payment_year = models.IntegerField(_("Year of payment"), default=2018)
    amount = models.DecimalField(_("Amount"), max_digits=10, decimal_places=2, default=0)
    is_valid = models.BooleanField(
        default=False,
        verbose_name=_("Valid?"),
    )
    created_at = models.DateTimeField(
        _("Created At"),
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        db_table = "staff_payments"
        verbose_name = _("Staff Payment")
        verbose_name_plural = _("Staff Payments")

    def __str__(self):
        return f"{self.sponsor} - {self.staff.first_name} {self.staff.last_name} - {self.month}"
