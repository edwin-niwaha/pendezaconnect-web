from django import forms
from django.core.exceptions import ValidationError

from core.profile_photos import normalize_profile_photo

from .models import (
    Child,
    ChildCorrespondence,
    ChildDepart,
    ChildIncident,
    ChildProfilePicture,
    ChildProgress,
)


def apply_standard_widgets(form):
    for field in form.fields.values():
        widget = field.widget
        css_class = widget.attrs.get("class", "")
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = f"{css_class} form-check-input".strip()
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = f"{css_class} form-select".strip()
        elif isinstance(widget, forms.FileInput):
            widget.attrs["class"] = f"{css_class} form-control".strip()
        else:
            widget.attrs["class"] = f"{css_class} form-control".strip()


class UploadForm(forms.Form):
    excel_file = forms.FileField()
    excel_file.widget.attrs["class"] = "form-control-file"


# =================================== CHILD FORM===================================


class ChildForm(forms.ModelForm):
    picture = forms.ImageField(
        required=False,
        label="Profile photo",
        widget=forms.FileInput(
            attrs={
                "accept": "image/jpeg,image/png,image/webp",
                "data-photo-input": "true",
            }
        ),
    )

    class Meta:
        model = Child
        exclude = ("is_departed", "is_sponsored")
        # date_of_birth = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "registration_date": forms.DateInput(attrs={"type": "date"}),
            "siblings": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "background_info": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "responsibility": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "mother_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "staff_comment": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "father_description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "c_interest": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "gender": forms.Select(attrs={"class": "form-control", "required": True}),
            "is_father_alive": forms.Select(attrs={"class": "form-control", "required": True}),
            "is_mother_alive": forms.Select(attrs={"class": "form-control", "required": True}),
            "religion": forms.Select(attrs={"class": "form-control", "required": True}),
            "is_child_in_school": forms.CheckboxInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)

    # Form validation
    def clean(self):
        super(ChildForm, self).clean()

        full_name = self.cleaned_data.get("full_name")

        if full_name and len(full_name) < 3:
            self.add_error("full_name", "Can not save first name less than 3 characters long")
            self.fields["full_name"].widget.attrs.update({"class": "form-control  is-invalid"})

        return self.cleaned_data

    def clean_picture(self):
        try:
            return normalize_profile_photo(self.cleaned_data.get("picture"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


# =================================== CHILD PROFILE ===================================
class ChildProfilePictureForm(forms.ModelForm):
    picture = forms.ImageField(required=False)

    class Meta:
        model = ChildProfilePicture
        fields = ["picture"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["picture"].widget = forms.FileInput(attrs={"accept": "image/*"})
        apply_standard_widgets(self)

    def clean_picture(self):
        try:
            return normalize_profile_photo(self.cleaned_data.get("picture"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


# =================================== CHILD  PROGRESS===================================
class ChildProgressForm(forms.ModelForm):
    class Meta:
        model = ChildProgress
        exclude = ("child",)

        widgets = {
            "name_of_school": forms.TextInput(attrs={"class": "form-control"}),
            "previous_schools": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "year": forms.NumberInput(attrs={"class": "form-control", "placeholder": "e.g. 2025"}),
            "term": forms.Select(attrs={"class": "form-select"}),
            "education_level": forms.Select(attrs={"class": "form-select"}),
            "child_class": forms.Select(attrs={"class": "form-select"}),
            "best_subject": forms.TextInput(attrs={"class": "form-control"}),
            "score": forms.NumberInput(attrs={"class": "form-control"}),
            "co_curricular_activity": forms.TextInput(attrs={"class": "form-control"}),
            "responsibility_at_school": forms.TextInput(attrs={"class": "form-control"}),
            "future_plans": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "responsibility_at_home": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)


# =================================== CHILD CORRESSPONDENCE ===================================
class ChildCorrespondenceForm(forms.ModelForm):
    class Meta:
        model = ChildCorrespondence
        exclude = ("child",)
        widgets = {
            "correspondence_type": forms.Select(attrs={"class": "form-control"}),
            "source": forms.Select(attrs={"class": "form-control"}),
            "attachment": forms.FileInput(attrs={"class": "form-control-file"}),
            "comment": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            # 'sponsor': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if not attachment:
            raise ValidationError("Attachment is required for all correspondence.")

        # Check if the attachment is a PDF file
        if not attachment.name.endswith(".pdf"):
            raise ValidationError("Only PDF attachments are allowed.")

        return attachment


# =================================== CHILD INCIDENT ===================================
class ChildIncidentForm(forms.ModelForm):
    class Meta:
        model = ChildIncident
        exclude = ("child",)
        widgets = {
            "incident_date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "attachment": forms.FileInput(attrs={"class": "form-control-file"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)

    def clean_attachment(self):
        attachment = self.cleaned_data.get("attachment")
        if not attachment:
            return attachment

        # Check if the attachment is a PDF file
        if not attachment.name.lower().endswith(".pdf"):
            raise ValidationError("Only PDF attachments are allowed.")

        return attachment


# =================================== CHILD DEPATURE ===================================
class ChildDepartForm(forms.ModelForm):
    class Meta:
        model = ChildDepart
        exclude = ("child",)
        widgets = {
            "depart_date": forms.DateInput(attrs={"type": "date", "required": True}),
            "depart_reason": forms.Textarea(attrs={"class": "form-control", "required": True, "rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_standard_widgets(self)
