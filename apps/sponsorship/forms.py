from django import forms
from django.core.exceptions import ValidationError

from .models import ChildSponsorship, StaffSponsorship


# =================================== Base Sponsorship Form ===================================
class BaseSponsorshipEditForm(forms.ModelForm):
    def clean(self):
        cleaned_data = super().clean()
        sponsor = cleaned_data.get("sponsor")
        start_date = cleaned_data.get("start_date")
        sponsorship_type = cleaned_data.get("sponsorship_type")

        # Check if a sponsorship with the same sponsor, start_date, and sponsorship_type already exists
        existing_sponsorship = self.Meta.model.objects.filter(
            sponsor=sponsor, start_date=start_date, sponsorship_type=sponsorship_type
        ).exclude(id=self.instance.id if self.instance else None)  # Exclude the current instance if editing

        if existing_sponsorship.exists():
            raise ValidationError("A sponsorship with the same details already exists.")

        return cleaned_data


# =================================== Child Sponsorship Form ===================================
class ChildSponsorshipForm(forms.ModelForm):
    class Meta:
        model = ChildSponsorship
        exclude = ("sponsor", "child", "is_active", "end_date")
        widgets = {
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date", "required": True}),
            "sponsorship_type": forms.Select(attrs={"class": "form-control", "required": True}),
        }


# =================================== Child Sponsorship Edit Form ===================================
class ChildSponsorshipEditForm(BaseSponsorshipEditForm):
    class Meta:
        model = ChildSponsorship
        fields = ("child", "sponsor", "start_date", "sponsorship_type")

        widgets = {
            "child": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "sponsor": forms.Select(attrs={"class": "form-control", "required": True}),
            "start_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "sponsorship_type": forms.Select(attrs={"class": "form-control", "required": True}),
        }


# =================================== Staff Sponsorship Form ===================================
class StaffSponsorshipForm(forms.ModelForm):
    class Meta:
        model = StaffSponsorship
        exclude = ("sponsor", "staff", "is_active", "end_date")
        widgets = {
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date", "required": True}),
            "sponsorship_type": forms.Select(attrs={"class": "form-control", "required": True}),  #
        }


# =================================== Staff Sponsorship Edit Form ===================================
class StaffSponsorshipEditForm(BaseSponsorshipEditForm):
    class Meta:
        model = StaffSponsorship
        fields = ("staff", "sponsor", "start_date", "sponsorship_type")

        widgets = {
            "staff": forms.Select(
                attrs={
                    "class": "form-control",
                }
            ),
            "sponsor": forms.Select(attrs={"class": "form-control", "required": True}),
            "start_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "sponsorship_type": forms.Select(attrs={"class": "form-control", "required": True}),
        }


# =================================== Payment Form ===================================
