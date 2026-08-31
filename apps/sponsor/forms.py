from django import forms

from .models import (
    Donor,
    Sponsor,
    SponsorDeparture,
    SponsorFeedback,
    sponsorship_type_flags,
)


def apply_standard_widgets(form):
    for field in form.fields.values():
        widget = field.widget
        css_class = widget.attrs.get("class", "")
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = f"{css_class} form-check-input".strip()
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = f"{css_class} form-select".strip()
        elif not isinstance(widget, forms.FileInput):
            widget.attrs["class"] = f"{css_class} form-control".strip()


# =================================== SPONSOR FORM ===================================
class SponsorForm(forms.ModelForm):
    class Meta:
        model = Sponsor
        exclude = ("is_departed",)
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "first_street_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "second_street_address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "gender": forms.Select(attrs={"class": "form-control", "required": True}),
            "sponsorship_type": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)

    # Form validation
    def clean(self):
        super(SponsorForm, self).clean()

        first_name = self.cleaned_data.get("first_name")
        last_name = self.cleaned_data.get("last_name")

        if first_name and len(first_name) < 2:
            self.add_error("first_name", "Can not save first name less than 2 characters long")
            self.fields["first_name"].widget.attrs.update({"class": "form-control  is-invalid"})

        if last_name and len(last_name) < 2:
            self.add_error("last_name", "Can not save last name less than 2 characters long")
            self.fields["last_name"].widget.attrs.update({"class": "form-control  is-invalid"})

        return self.cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        for field, value in sponsorship_type_flags(instance.sponsorship_type).items():
            if value:
                setattr(instance, field, True)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


# =================================== DONOR FORM ===================================
class DonorForm(forms.ModelForm):
    class Meta:
        model = Donor
        fields = ["full_name", "email", "phone"]

        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Full Name",
                    "required": True,
                }
            ),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Email"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Phone Number"}),
        }


# =================================== SPONSOR DEPATURE ===================================
class SponsorDepartForm(forms.ModelForm):
    class Meta:
        model = SponsorDeparture
        exclude = ("sponsor",)
        widgets = {
            "departure_date": forms.DateInput(attrs={"type": "date"}),
            "departure_reason": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)


class SponsorFeedbackForm(forms.ModelForm):
    class Meta:
        model = SponsorFeedback
        fields = ("subject", "message")
        widgets = {
            "subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "maxlength": 150,
                    "placeholder": "What would you like us to know?",
                    "required": True,
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": "Share feedback, a concern, a question, or an update for the sponsorship team.",
                    "required": True,
                }
            ),
        }


# =================================== SPONSOR upload ===================================


class SponsorUploadForm(forms.Form):
    excel_file = forms.FileField()
    excel_file.widget.attrs["class"] = "form-control-file"
