from datetime import datetime

from django import forms
from django.utils.translation import gettext_lazy as _

from .models import (
    ChildPayments,
    DonorPayment,
    Payment,
    StaffPayments,
    SupportProgram,
)

SPONSOR_LEVEL_PROGRAM_LABELS = {
    SupportProgram.FAMILY_SUPPORT: "Family Full Support",
    SupportProgram.FAMILY_CO_SUPPORT: "Family Co-support",
    SupportProgram.GENERAL_SUPPORT: "General Support",
    SupportProgram.ONE_TIME_DONATION: "One-time Donation",
}


class SupportProgramChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return SPONSOR_LEVEL_PROGRAM_LABELS.get(obj.code, obj.name)


# =================================== Child Payments Form ===================================
class ChildPaymentForm(forms.ModelForm):
    current_year = datetime.now().year

    payment_year = forms.IntegerField(
        label=_("Year of payment"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "type": "number",
                "required": True,
            }
        ),
        min_value=2018,
        max_value=current_year,
    )

    class Meta:
        model = ChildPayments
        exclude = (
            "sponsor",
            "child",
            "is_valid",
        )

        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "month": forms.Select(attrs={"class": "form-control", "required": True}),
            "amount": forms.NumberInput(attrs={"type": "number", "required": True}),
        }

    def clean_payment_year(self):
        payment_year = self.cleaned_data["payment_year"]

        # Example custom validation: Ensure payment_year is within a specific range
        if payment_year < 2018 or payment_year > self.current_year:
            raise forms.ValidationError(f"Payment year must be between 2018 and {self.current_year}.")

        # Add more validation as needed

        return payment_year


# =================================== Donor Payments Form ===================================


class DonorPaymentForm(forms.ModelForm):
    class Meta:
        model = DonorPayment
        exclude = ("donor",)

        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "amount": forms.NumberInput(attrs={"type": "number", "required": True}),
        }


# =================================== Child Payment Edit Form ===================================
class ChildPaymentEditForm(forms.ModelForm):
    class Meta:
        model = ChildPayments
        exclude = (
            "sponsor",
            "child",
            "is_valid",
        )

        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "month": forms.Select(attrs={"class": "form-control", "required": True}),
            "amount": forms.NumberInput(attrs={"type": "number", "required": True}),
        }


# =================================== Staff Payments Form ===================================
class StaffPaymentForm(forms.ModelForm):
    current_year = datetime.now().year

    payment_year = forms.IntegerField(
        label=_("Year of payment"),
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "type": "number",
                "required": True,
            }
        ),
        min_value=2023,
        max_value=current_year,
    )

    class Meta:
        model = StaffPayments
        exclude = (
            "sponsor",
            "staff",
            "is_valid",
        )

        widgets = {
            "payment_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                    "required": True,
                }
            ),
            "month": forms.Select(attrs={"class": "form-control", "required": True}),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "type": "number",
                    "required": True,
                    "min": "0",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
        }

    def clean_payment_year(self):
        payment_year = self.cleaned_data["payment_year"]

        # Example custom validation: Ensure payment_year is within a specific range
        if payment_year < 2023 or payment_year > self.current_year:
            raise forms.ValidationError(f"Payment year must be between 2023 and {self.current_year}.")

        # Add more validation as needed

        return payment_year


# =================================== Staff Payment Edit Form ===================================
class StaffPaymentEditForm(forms.ModelForm):
    class Meta:
        model = StaffPayments
        exclude = (
            "sponsor",
            "staff",
            "is_valid",
        )

        widgets = {
            "payment_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                    "required": True,
                }
            ),
            "month": forms.Select(attrs={"class": "form-control", "required": True}),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "type": "number",
                    "required": True,
                    "min": "0",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
        }


class SponsorLevelPaymentForm(forms.ModelForm):
    ALLOWED_PROGRAMS = (
        SupportProgram.FAMILY_SUPPORT,
        SupportProgram.FAMILY_CO_SUPPORT,
        SupportProgram.GENERAL_SUPPORT,
        SupportProgram.ONE_TIME_DONATION,
    )
    program = SupportProgramChoiceField(
        label="Payment category",
        queryset=SupportProgram.objects.none(),
        empty_label="Select payment category",
        widget=forms.Select(
            attrs={
                "class": "form-control",
                "required": True,
            }
        ),
    )

    class Meta:
        model = Payment
        fields = ("program", "payment_date", "amount", "reference", "notes")
        widgets = {
            "payment_date": forms.DateInput(
                attrs={
                    "class": "form-control",
                    "type": "date",
                    "required": True,
                }
            ),
            "amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "type": "number",
                    "required": True,
                    "min": "0",
                    "step": "0.01",
                    "placeholder": "0.00",
                }
            ),
            "reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Receipt, mobile money, or bank reference",
                }
            ),
            "notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional note for this payment",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["program"].queryset = SupportProgram.objects.filter(
            code__in=self.ALLOWED_PROGRAMS,
            is_active=True,
        ).order_by("name")
