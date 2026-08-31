import phonenumbers
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

# class Supplier(models.Model):
#     name = models.CharField(max_length=255, verbose_name="Supplier Name")
#     contact_name = models.CharField(max_length=255, verbose_name="Contact Name")
#     email = models.EmailField(verbose_name="Email Address")
#     phone = PhoneNumberField(
#         null=True, blank=True, default="+12125552368", verbose_name="Telephone"
#     )
#     address = models.CharField(max_length=255, verbose_name="Address")
#     created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")

#     def __str__(self):
#         return self.name

#     def clean(self):
#         self.validate_name()
#         self.validate_email()
#         self.validate_phone()

#     def validate_name(self):
#         if not self.name.strip():
#             raise ValidationError("Supplier name cannot be empty.")

#     def validate_email(self):
#         if not self.email:
#             raise ValidationError("Email address cannot be empty.")

#     def validate_phone(self):
#         if self.phone:
#             try:
#                 parsed_phone = phonenumbers.parse(str(self.phone), None)
#                 if not phonenumbers.is_valid_number(parsed_phone):
#                     raise ValidationError("Phone number is invalid.")
#             except phonenumbers.NumberParseException:
#                 raise ValidationError("Phone number could not be parsed.")


class Supplier(models.Model):
    name = models.CharField(max_length=255, verbose_name="Supplier Name")
    contact_name = models.CharField(max_length=255, verbose_name="Contact Name")
    email = models.EmailField(verbose_name="Email Address")
    phone = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        default="+12125552368",
        verbose_name="Telephone",
    )
    address = models.CharField(max_length=255, verbose_name="Address")
    created_at = models.DateTimeField(default=timezone.now, verbose_name="Created At")

    def __str__(self):
        return self.name

    def clean(self):
        self.validate_name()
        self.validate_email()
        self.validate_phone()

    def validate_name(self):
        if not self.name.strip():
            raise ValidationError("Supplier name cannot be empty.")

    def validate_email(self):
        if not self.email:
            raise ValidationError("Email address cannot be empty.")

    def validate_phone(self):
        if self.phone:
            # Check if phone number starts with '+'
            if not self.phone.startswith("+"):
                raise ValidationError("Phone number must start with a '+'.")

            # Check phone number length
            phone_length = len(self.phone)
            if phone_length < 8 or phone_length > 15:
                raise ValidationError("Phone number must be between 8 and 15 characters long.")

            # Validate phone number format
            try:
                parsed_phone = phonenumbers.parse(self.phone, None)
                if not phonenumbers.is_valid_number(parsed_phone):
                    raise ValidationError("Phone number is invalid.")
            except phonenumbers.NumberParseException:
                raise ValidationError("Phone number could not be parsed.")
