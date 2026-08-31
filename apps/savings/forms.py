import re

from django import forms
from django.utils import timezone

from apps.client.models import Client

from .models import SavingsAccount, SavingsTransaction


class SavingsAccountForm(forms.ModelForm):
    client = forms.ModelChoiceField(
        queryset=Client.objects.order_by("full_name", "reg_number"),
        widget=forms.Select(
            attrs={
                "class": "form-control",
                "data-client-search-select": "true",
            }
        ),
        empty_label="Select client",
    )

    class Meta:
        model = SavingsAccount
        fields = ["client", "account_number", "opening_date", "status", "notes"]
        widgets = {
            "account_number": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Leave blank to auto-generate",
                }
            ),
            "opening_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }


class SavingsTransactionForm(forms.ModelForm):
    account = forms.ModelChoiceField(
        queryset=SavingsAccount.objects.select_related("client").filter(status="active"),
        widget=forms.Select(
            attrs={
                "class": "form-control",
                "data-account-search-select": "true",
            }
        ),
        empty_label="Select savings account",
    )

    class Meta:
        model = SavingsTransaction
        fields = [
            "account",
            "transaction_type",
            "amount",
            "transaction_date",
            "payment_method",
            "reference",
            "notes",
            "status",
        ]
        widgets = {
            "transaction_type": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "transaction_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "status": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        account = kwargs.pop("account", None)
        super().__init__(*args, **kwargs)
        self.fields["transaction_date"].initial = self.fields["transaction_date"].initial or timezone.localdate()
        if account is not None:
            self.fields["account"].initial = account
            self.fields["account"].widget = forms.HiddenInput()


class ClientSavingsRequestForm(forms.ModelForm):
    class Meta:
        model = SavingsTransaction
        fields = ["transaction_type", "amount", "payment_method", "reference", "notes"]
        widgets = {
            "transaction_type": forms.Select(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": "0.01", "step": "0.01"}),
            "payment_method": forms.Select(attrs={"class": "form-control"}),
            "reference": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Mobile money or bank reference",
                }
            ),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        transaction_type = kwargs.pop("transaction_type", None)
        super().__init__(*args, **kwargs)
        choices = [("deposit", "Deposit request"), ("withdrawal", "Withdrawal request")]
        self.fields["transaction_type"].choices = choices
        if transaction_type:
            self.fields["transaction_type"].initial = transaction_type
            self.fields["transaction_type"].widget = forms.HiddenInput()
            self.fields["transaction_type"].required = False


class ClientMobileMoneyDepositForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=15,
        decimal_places=2,
        min_value=5000,
        widget=forms.NumberInput(
            attrs={
                "class": "form-control",
                "min": "5000",
                "step": "100",
                "placeholder": "Minimum 5,000 UGX",
            }
        ),
        error_messages={"min_value": "Amount must be 5,000 UGX or more."},
    )
    phone = forms.CharField(
        max_length=10,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "07XXXXXXXX",
                "inputmode": "numeric",
            }
        ),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "rows": 2,
                "placeholder": "Optional note for your statement",
            }
        ),
    )

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip().replace(" ", "")
        if not re.match(r"^07\d{8}$", phone):
            raise forms.ValidationError("Enter a valid MTN mobile money number, for example 0771234567.")
        return phone
