from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from apps.client.models import Client
from apps.sponsor.models import Sponsor

from .models import Contact, DocumentUpload, Ebook, Policy, Profile


# =================================== Register  ===================================
class RegisterForm(UserCreationForm):
    # fields we want to include and customize in our form
    first_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "First Name",
                "class": "form-control",
            }
        ),
    )
    last_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Last Name",
                "class": "form-control",
            }
        ),
    )
    username = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Username",
                "class": "form-control",
            }
        ),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Email",
                "class": "form-control",
            }
        ),
    )
    password1 = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Password",
                "class": "form-control",
                "data-toggle": "password",
                "id": "password",
            }
        ),
    )
    password2 = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Confirm Password",
                "class": "form-control",
                "data-toggle": "password",
                "id": "password",
            }
        ),
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "email",
            "password1",
            "password2",
        ]


# =================================== Login  ===================================
class LoginForm(AuthenticationForm):
    username = forms.CharField(
        max_length=100,
        required=True,
        label="Email or username",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Email or username",
                "class": "form-control",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.PasswordInput(
            attrs={
                "placeholder": "Password",
                "class": "form-control",
                "data-toggle": "password",
                "id": "password",
                "name": "password",
            }
        ),
    )
    remember_me = forms.BooleanField(required=False)

    class Meta:
        model = User
        fields = ["username", "password", "remember_me"]

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if "@" not in username:
            return username

        user = User.objects.filter(email__iexact=username).order_by("id").first()
        if user:
            return user.get_username()
        return username


class LoginVerificationForm(forms.Form):
    token = forms.CharField(
        max_length=6,
        min_length=6,
        label="Verification code",
        widget=forms.TextInput(
            attrs={
                "placeholder": "Enter 6-digit code",
                "class": "form-control",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
            }
        ),
    )

    def clean_token(self):
        token = self.cleaned_data.get("token", "").strip()
        if not token.isdigit():
            raise forms.ValidationError("Enter the 6-digit code sent to your email.")
        return token


# =================================== User Update  ===================================
class UpdateUserForm(forms.ModelForm):
    username = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    email = forms.EmailField(required=True, widget=forms.TextInput(attrs={"class": "form-control"}))

    class Meta:
        model = User
        fields = ["username", "email"]


# =================================== Pofile Update  ===================================


class UpdateProfileForm(forms.ModelForm):
    avatar = forms.ImageField(widget=forms.FileInput(attrs={"class": "form-control-file"}))
    bio = forms.CharField(widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}))

    class Meta:
        model = Profile
        fields = ["avatar", "bio"]
        widgets = {
            "role": forms.Select(attrs={"class": "form-control", "required": True}),
        }


# =================================== Pofile Update * ===================================


class UpdateProfileAllForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.order_by("full_name", "reg_number"),
        required=False,
        empty_label="No linked client",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    sponsor = forms.ModelChoiceField(
        queryset=Sponsor.objects.order_by("first_name", "last_name", "email"),
        required=False,
        empty_label="No linked sponsor",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = Profile
        fields = ["account_type", "staff_role", "role", "client", "sponsor"]
        widgets = {
            "account_type": forms.Select(attrs={"class": "form-control"}),
            "staff_role": forms.Select(attrs={"class": "form-control"}),
            "role": forms.Select(attrs={"class": "form-control", "required": True}),
        }


# =================================== Contact Form  ===================================
class ContactForm(forms.ModelForm):
    class Meta:
        model = Contact
        exclude = ("is_valid",)
        widgets = {
            "message": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if not email:
            raise forms.ValidationError("Email field is required")
        return email

    def clean_message(self):
        message = self.cleaned_data.get("message")
        if not message:
            raise forms.ValidationError("Message field is required")
        return message


# =================================== Policy Form  ===================================
class PolicyForm(forms.ModelForm):
    class Meta:
        model = Policy
        exclude = ("is_valid",)

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Policy title",
                    "required": True,
                }
            ),
            "upload": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "application/pdf,.pdf",
                }
            ),
            "date_reviewed": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean_upload(self):
        upload = self.cleaned_data.get("upload")
        if upload:
            if not upload.name.lower().endswith(".pdf"):
                raise forms.ValidationError("Only PDF files are allowed.")
            if upload.size > 10 * 1024 * 1024:  # 10 MB limit
                raise forms.ValidationError("The file is too large. It should be less than 10 MB.")
        return upload


# =================================== Ebook Form  ===================================


class EbookUploadForm(forms.ModelForm):
    class Meta:
        model = Ebook
        fields = ["title", "author", "ebook_file"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Book title"}),
            "author": forms.TextInput(attrs={"class": "form-control", "placeholder": "Author"}),
            "ebook_file": forms.FileInput(attrs={"class": "form-control", "accept": "application/pdf,.pdf"}),
        }

    def clean_ebook_file(self):
        ebook_file = self.cleaned_data.get("ebook_file")
        if ebook_file and not ebook_file.name.lower().endswith(".pdf"):
            raise forms.ValidationError("Only PDF ebook files are allowed.")
        return ebook_file


# =================================== Document Form  ===================================


class DocumentForm(forms.ModelForm):
    class Meta:
        model = DocumentUpload
        fields = "__all__"
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Document title"}),
            "file": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "application/pdf,.pdf,.xls,.xlsx",
                }
            ),
        }
