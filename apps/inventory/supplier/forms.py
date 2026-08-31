# forms.py
from django import forms

from .models import Supplier


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = ["name", "contact_name", "email", "phone", "address"]

    def clean(self):
        cleaned_data = super().clean()

        # Validate supplier name
        if not cleaned_data.get("name"):
            raise forms.ValidationError("Supplier name cannot be empty.")

        # Validate email address
        if not cleaned_data.get("email"):
            raise forms.ValidationError("Email address cannot be empty.")

        # Validate phone number
        phone = cleaned_data.get("phone")
        if phone:
            # Convert PhoneNumber object to string for validation
            phone_str = str(phone)
            if not phone_str.replace("+", "").isdigit():
                raise forms.ValidationError("Phone number must contain only digits.")

            # Check phone number length
            phone_length = len(phone)
            if phone_length < 8 or phone_length > 15:
                raise forms.ValidationError("Phone number must be between 8 and 15 characters long.")

        return cleaned_data  # Don't forget to return cleaned_data!
