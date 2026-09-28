import datetime
from datetime import date

from cloudinary.models import CloudinaryField
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    EmailValidator,
    FileExtensionValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.utils import timezone
from phonenumber_field.modelfields import PhoneNumberField


# Clients registration
class Client(models.Model):
    GENDER_CHOICES = (
        ("Male", "Male"),
        ("Female", "Female"),
    )
    # Basic info
    reg_number = models.CharField(
        max_length=50,
        verbose_name="Reg. No",
        null=True,
        blank=True,
        default="",
    )
    full_name = models.CharField(
        max_length=255,
        verbose_name="Full Name",
    )
    gender = models.CharField(max_length=6, choices=GENDER_CHOICES, blank=True, default="", verbose_name="Gender")
    email = models.EmailField(
        verbose_name="Email",
        blank=True,
        default="",
        validators=[
            RegexValidator(
                r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                message="Enter a valid email address.",
            )
        ],
    )
    picture = CloudinaryField(
        "client_uploads",
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png"])],
        null=True,
        blank=True,
    )
    mobile_telephone = PhoneNumberField(verbose_name="Mobile Telephone", null=True, blank=True, default="", region="UG")
    client_type = models.CharField(
        max_length=20,
        choices=[
            ("individual", "Individual"),
            ("group", "Group"),
            ("joint", "Joint"),
            ("organization", "Organization"),
        ],
        default="individual",
        verbose_name="Client type",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    registration_date = models.DateField(null=True, blank=True)
    village = models.CharField(max_length=150, blank=True)
    current_address = models.TextField(blank=True)
    workplace = models.CharField(max_length=255, blank=True)
    occupation = models.CharField(max_length=150, blank=True)
    employment_status = models.CharField(max_length=100, blank=True)
    employment_sector = models.CharField(max_length=100, blank=True)
    marital_status = models.CharField(max_length=50, blank=True)
    highest_education_level = models.CharField(max_length=100, blank=True)
    next_of_kin_name = models.CharField(max_length=255, blank=True)
    next_of_kin_phone = PhoneNumberField(blank=True, region="UG")
    next_of_kin_relationship = models.CharField(max_length=100, blank=True)
    referred_by = models.CharField(max_length=255, blank=True)
    savings_goal = models.TextField(blank=True)
    services_interested = models.TextField(blank=True, verbose_name="Services interested in")
    savings_frequency = models.CharField(
        max_length=20,
        blank=True,
        choices=[
            ("daily", "Daily"),
            ("weekly", "Weekly"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("annually", "Annually"),
            ("irregular", "Irregular"),
        ],
    )
    minimum_savings_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    group_member_count = models.PositiveIntegerField(null=True, blank=True)
    group_objective = models.TextField(blank=True)
    group_savings_cycle_months = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)])
    group_chairperson = models.CharField(max_length=255, blank=True)
    group_secretary = models.CharField(max_length=255, blank=True)
    group_treasurer = models.CharField(max_length=255, blank=True)
    branch = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_info"
        verbose_name = "Client Bio Data"
        verbose_name_plural = "Clients Bio Data"

    def __str__(self):
        return self.full_name

    def clean(self):
        super().clean()
        errors = {}
        today = timezone.localdate()
        for field in ("date_of_birth", "registration_date"):
            value = getattr(self, field)
            if value and value > today:
                errors[field] = "Date cannot be in the future."
        if self.date_of_birth and self.registration_date and self.date_of_birth > self.registration_date:
            errors["registration_date"] = "Registration date cannot be before date of birth."
        if errors:
            raise ValidationError(errors)

    def get_full_name(self):
        return f"{self.full_name}".strip()

    def to_select2(self):
        return {"label": self.get_full_name(), "value": self.id}


class ClientProfilePicture(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="profile_pictures",
        verbose_name="Client",
    )
    picture = CloudinaryField(
        "client_uploads",
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png"])],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Uploaded at")
    is_current = models.BooleanField(default=False, verbose_name="Is Current Picture")

    class Meta:
        db_table = "client_pictures"
        verbose_name = "Client Profile Picture"
        verbose_name_plural = "Client Profile Pictures"
        ordering = ["-uploaded_at", "-id"]

    def __str__(self):
        return f"{self.client.full_name} - {self.uploaded_at:%Y-%m-%d}"


# 7Hills registration
class SevenHillsRegistration(models.Model):
    registration_date = models.DateField()
    full_name = models.CharField(max_length=255)
    GENDER_CHOICES = [
        ("M", "Male"),
        ("F", "Female"),
    ]
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField(
        null=True,
        blank=True,
        verbose_name="Date of Birth",
        default=None,
    )

    AGE_BRACKET_CHOICES = [
        ("0-17", "0 – 17"),
        ("18-25", "18 – 25"),
        ("26-34", "26 – 34"),
        ("35-45", "35 – 45"),
        ("46+", "46 and above"),
    ]
    age_bracket = models.CharField(max_length=10, choices=AGE_BRACKET_CHOICES)

    MARITAL_STATUS_CHOICES = [
        ("Single", "Single"),
        ("Married", "Married"),
        ("Widowed", "Widowed"),
        ("Divorced", "Divorced"),
        ("Domestic Partnership", "In a Domestic Partnership"),
    ]
    marital_status = models.CharField(max_length=50, choices=MARITAL_STATUS_CHOICES)
    spouse_name = models.CharField(max_length=255, blank=True, null=True)
    spouse_contact = PhoneNumberField(blank=True, null=True)

    number_of_children = models.PositiveIntegerField(blank=True, null=True)
    boys = models.PositiveIntegerField(blank=True, null=True)
    girls = models.PositiveIntegerField(blank=True, null=True)

    CHILDREN_AGE_BRACKETS = [
        ("0-5", "0-5 years"),
        ("6-10", "6-10 years"),
        ("11-15", "11-15 years"),
        ("16-18", "16-18 years"),
    ]
    children_age_brackets = models.CharField(max_length=20, blank=True, null=True)

    highest_education = models.CharField(max_length=255, blank=True, null=True)
    home_village = models.CharField(max_length=255, blank=True, null=True)
    residence = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(validators=[EmailValidator()], blank=True, null=True)
    telephone_1 = PhoneNumberField(blank=True, null=True)
    telephone_2 = PhoneNumberField(blank=True, null=True)

    next_of_kin = models.CharField(max_length=255, blank=True, null=True)
    next_of_kin_telephone_1 = PhoneNumberField(blank=True, null=True)
    next_of_kin_telephone_2 = PhoneNumberField(blank=True, null=True)
    relationship_with_next_of_kin = models.CharField(max_length=255, blank=True, null=True)

    workplace = models.CharField(max_length=255, blank=True, null=True)

    SAVINGS_FREQUENCY_CHOICES = [
        ("Daily", "Daily"),
        ("Weekly", "Weekly"),
        ("Monthly", "Monthly"),
    ]
    savings_frequency = models.CharField(max_length=10, choices=SAVINGS_FREQUENCY_CHOICES, blank=True, null=True)
    min_savings_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    saving_goal = models.TextField(blank=True, null=True)

    SERVICES_INTERESTED = [
        ("Savings Scheme", "Join Savings Scheme"),
        ("Skills Training", "Skills Training"),
        ("Share Group", "Join Share Group"),
        ("Community Unit", "Join Community Unit"),
        ("Discipleship", "Discipleship"),
        ("Volunteering", "Volunteering"),
    ]
    services_interested = models.TextField(blank=True, null=True)

    MINISTRY_GROUPS = [
        ("Ushering", "Ushering"),
        ("Evangelism", "Evangelism"),
        ("Children Ministry", "Children's Ministry"),
        ("Youth Ministry", "Youth Ministry"),
        ("Intercession", "Intercession"),
        ("Choir", "Choir"),
        ("Hospitality", "Hospitality"),
        ("Media", "Media"),
    ]
    ministry_groups = models.TextField(blank=True, null=True)

    dc_makerere_association_year = models.PositiveIntegerField(
        blank=True, null=True, validators=[MinValueValidator(1900)]
    )
    recommended_by = models.CharField(max_length=255, blank=True, null=True)
    preferred_contact_method = models.CharField(max_length=255, blank=True, null=True)
    additional_comments = models.TextField(blank=True, null=True)
    agrees_to_photo_use = models.BooleanField(default=False)

    class Meta:
        db_table = "seven_hills_registration"

    def clean(self):
        # Validate that date_of_birth is not in the future
        if self.date_of_birth and self.date_of_birth > datetime.date.today():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})
        # Validate that registration_date is not in the future
        if self.registration_date and self.registration_date > datetime.date.today():
            raise ValidationError({"registration_date": "Registration date cannot be in the future."})
        # Call the parent clean method to ensure other validations still work
        super().clean()

    def __str__(self):
        return f"{self.full_name}"

    # Convert services_interested field (comma-separated string) to human-readable form
    def get_services_interested_display(self):
        services_dict = {
            "Savings Scheme": "Join Savings Scheme",
            "Skills Training": "Skills Training",
            "Share Group": "Join Share Group",
            "Community Unit": "Join Community Unit",
            "Discipleship": "Discipleship",
            "Volunteering": "Volunteering",
        }
        if self.services_interested:
            selected_services = self.services_interested.split(",")
            return ", ".join([services_dict.get(service.strip(), service) for service in selected_services])
        return ""

    # Convert ministry_groups field (comma-separated string) to human-readable form
    def get_ministry_groups_display(self):
        ministries_dict = {
            "Ushering": "Ushering",
            "Evangelism": "Evangelism",
            "Children Ministry": "Children's Ministry",
            "Youth Ministry": "Youth Ministry",
            "Intercession": "Intercession",
            "Choir": "Choir",
            "Hospitality": "Hospitality",
            "Media": "Media",
        }
        if self.ministry_groups:
            selected_ministries = self.ministry_groups.split(",")
            return ", ".join([ministries_dict.get(ministry.strip(), ministry) for ministry in selected_ministries])
        return ""

    @property
    def prefixed_id(self):
        if self.pk < 10:
            return f"7H00{self.pk}"
        elif self.pk < 100:
            return f"7H0{self.pk}"
        else:
            return f"7H{self.pk}"

    def calculate_age(self):
        today = date.today()
        age = (
            today.year
            - self.date_of_birth.year
            - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        )
        return age


class ClientRegistrationDraft(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    data = models.JSONField(default=dict)
    step = models.PositiveSmallIntegerField(default=0)
    revision = models.PositiveIntegerField(default=0)
    photo = models.BinaryField(null=True, blank=True)
    photo_name = models.CharField(max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
