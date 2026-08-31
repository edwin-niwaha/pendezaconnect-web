import datetime
from datetime import date

from cloudinary.models import CloudinaryField
from django.core.exceptions import ValidationError
from django.core.validators import (
    EmailValidator,
    FileExtensionValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


# Clients registration
class Client(models.Model):
    # Basic info
    reg_number = models.CharField(
        max_length=10,
        verbose_name="Registration ID",
        null=True,
        blank=True,
        default="G01-001",
    )
    full_name = models.CharField(
        max_length=50,
        verbose_name="Full Name",
        validators=[RegexValidator(r"^[A-Za-z]+(?:\s[A-Za-z]+)*$", "Only letters and spaces are allowed")],
    )
    email = models.EmailField(
        verbose_name="Email",
        blank=True,
        default="no-email@example.com",
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
    mobile_telephone = PhoneNumberField(verbose_name="Mobile Telephone", null=True, blank=True, default="+256999999999")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_info"
        verbose_name = "Client Bio Data"
        verbose_name_plural = "Clients Bio Data"

    def __str__(self):
        return self.full_name

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
