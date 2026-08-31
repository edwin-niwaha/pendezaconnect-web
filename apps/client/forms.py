from crispy_forms.helper import FormHelper
from crispy_forms.layout import ButtonHolder, Fieldset, Layout, Submit
from django import forms

from core.profile_photos import normalize_profile_photo

from .models import Client, SevenHillsRegistration


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["picture"].required = False
        self.fields["picture"].widget.attrs.update(
            {"accept": "image/jpeg,image/png,image/webp", "data-photo-input": "true"}
        )

    def clean_picture(self):
        try:
            return normalize_profile_photo(self.cleaned_data.get("picture"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name")
        if len(full_name) < 3:
            raise forms.ValidationError("Full name must be at least 3 characters long.")
        return full_name

    def clean(self):
        cleaned_data = super().clean()
        full_name = cleaned_data.get("full_name")

        if full_name and len(full_name) < 3:
            self.add_error("full_name", "Full name must be at least 3 characters long.")
            self.fields["full_name"].widget.attrs.update({"class": "form-control is-invalid"})

        return cleaned_data


class ClientPhotoForm(forms.Form):
    picture = forms.ImageField(
        label="Photo",
        required=False,
        widget=forms.FileInput(
            attrs={
                "accept": "image/jpeg,image/png,image/webp",
                "data-photo-input": "true",
            }
        ),
    )

    def clean_picture(self):
        try:
            return normalize_profile_photo(self.cleaned_data.get("picture"))
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


# Import form
class ImportClientsForm(forms.Form):
    excel_file = forms.FileField()
    excel_file.widget.attrs["class"] = "form-control-file"


class SevenHillsRegistrationForm(forms.ModelForm):
    class Meta:
        model = SevenHillsRegistration
        fields = "__all__"
        widgets = {
            "registration_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "date_of_birth": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "telephone_1": forms.TextInput(attrs={"class": "form-control"}),
            "telephone_2": forms.TextInput(attrs={"class": "form-control"}),
            "next_of_kin_telephone_1": forms.TextInput(attrs={"class": "form-control"}),
            "next_of_kin_telephone_2": forms.TextInput(attrs={"class": "form-control"}),
            "min_savings_amount": forms.NumberInput(attrs={"class": "form-control"}),
            "saving_goal": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "additional_comments": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    # Custom fields
    services_interested = forms.MultipleChoiceField(
        choices=SevenHillsRegistration.SERVICES_INTERESTED,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    ministry_groups = forms.MultipleChoiceField(
        choices=SevenHillsRegistration.MINISTRY_GROUPS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name")
        if len(full_name) < 3:
            raise forms.ValidationError("Full name must be at least 3 characters long.")
        return full_name

    def clean(self):
        cleaned_data = super().clean()
        spouse_name = cleaned_data.get("spouse_name")
        marital_status = cleaned_data.get("marital_status")

        if marital_status == "Married" and not spouse_name:
            self.add_error("spouse_name", "Spouse name is required for married individuals.")

        return cleaned_data

    def clean_services_interested(self):
        services_interested = self.cleaned_data.get("services_interested")
        valid_services = [choice[0] for choice in SevenHillsRegistration.SERVICES_INTERESTED]
        invalid_choices = [choice for choice in services_interested if choice not in valid_services]
        if invalid_choices:
            raise forms.ValidationError(f"Invalid services: {', '.join(invalid_choices)}")
        return services_interested

    def clean_ministry_groups(self):
        ministry_groups = self.cleaned_data.get("ministry_groups")
        valid_groups = [choice[0] for choice in SevenHillsRegistration.MINISTRY_GROUPS]
        invalid_choices = [choice for choice in ministry_groups if choice not in valid_groups]
        if invalid_choices:
            raise forms.ValidationError(f"Invalid ministry groups: {', '.join(invalid_choices)}")
        return ministry_groups

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Adding crispy form helper for layout customization
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Fieldset(
                "Services Interested",
                "services_interested",
            ),
            Fieldset(
                "Ministry Groups",
                "ministry_groups",
            ),
            ButtonHolder(Submit("submit", "Submit", css_class="btn btn-primary")),
        )
