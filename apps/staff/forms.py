from cloudinary import CloudinaryResource
from django import forms

from .models import Staff, StaffDeparture

# =================================== STAFF FORM ===================================


class StaffForm(forms.ModelForm):
    class Meta:
        model = Staff
        exclude = ("is_departed", "is_sponsored")
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "last_name": forms.TextInput(attrs={"class": "form-control", "required": True}),
            "picture": forms.FileInput(attrs={"class": "form-control-file", "accept": "image/*"}),
            "date_of_birth": forms.DateInput(attrs={"class": "form-control", "type": "date", "required": True}),
            "email": forms.EmailInput(attrs={"class": "form-control", "required": True}),
            "home_district": forms.TextInput(attrs={"class": "form-control"}),
            "mobile_telephone": forms.TextInput(attrs={"class": "form-control"}),
            "date_started_work": forms.DateInput(attrs={"class": "form-control", "type": "date", "required": True}),
            "gender": forms.Select(attrs={"class": "form-control", "required": True}),
            "marital_status": forms.Select(attrs={"class": "form-control", "required": True}),
            "department": forms.Select(attrs={"class": "form-control", "required": True}),
            "job_title": forms.TextInput(attrs={"class": "form-control"}),
        }

    # Form validation
    def clean(self):
        super(StaffForm, self).clean()

        first_name = self.cleaned_data.get("first_name")
        last_name = self.cleaned_data.get("last_name")

        if first_name and len(first_name) < 3:
            self.add_error("first_name", "Can not save first name less than 3 characters long")
            self.fields["first_name"].widget.attrs.update({"class": "form-control  is-invalid"})

        if last_name and len(last_name) < 3:
            self.add_error("last_name", "Can not save last name less than 3 characters long")
            self.fields["last_name"].widget.attrs.update({"class": "form-control  is-invalid"})

        return self.cleaned_data


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = Staff
        exclude = ("is_departed", "is_sponsored", "created_at", "updated_at")
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date", "required": True}),
            "date_started_work": forms.DateInput(attrs={"type": "date", "required": True}),
            "gender": forms.Select(attrs={"class": "form-control", "required": True}),
            "marital_status": forms.Select(attrs={"class": "form-control", "required": True}),
            "department": forms.Select(attrs={"class": "form-control", "required": True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["picture"].widget = forms.FileInput(attrs={"accept": "image/*"})

    def clean_picture(self):
        picture = self.cleaned_data.get("picture")

        # Allow empty uploads
        if not picture:
            return picture

        # Handle Cloudinary images correctly
        if isinstance(picture, CloudinaryResource):
            return picture  # Cloudinary handles storage

        # Check file size (for non-Cloudinary uploads)
        if getattr(picture, "size", 0) > 10 * 1024 * 1024:  # 10 MB
            raise forms.ValidationError("Image size should not exceed 10 MB.")

        return picture


# =================================== STAFF DEPATURE ===================================
class StaffDepartureForm(forms.ModelForm):
    class Meta:
        model = StaffDeparture
        exclude = ("staff",)
        widgets = {
            "departure_date": forms.DateInput(attrs={"class": "form-control", "type": "date", "required": True}),
            "departure_reason": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Record the reason for departure",
                    "required": True,
                }
            ),
        }
