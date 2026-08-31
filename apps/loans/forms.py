import logging
import os
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.client.models import Client

from .models import (
    LOAN_DOCUMENT_ALLOWED_EXTENSIONS,
    ChartOfAccounts,
    Loan,
    LoanApplicationDocument,
    LoanDisbursement,
    LoanPenalty,
    LoanRepayment,
)

logger = logging.getLogger(__name__)

# Account number range for cash/bank accounts used in disbursements and repayments
MIN_ACCOUNT_NUMBER = 1010
MAX_ACCOUNT_NUMBER = 1020


# ─────────────────────────────────────────────────────────────────────────────
# Import forms
# ─────────────────────────────────────────────────────────────────────────────


class ImportLoansForm(forms.Form):
    excel_file = forms.FileField(widget=forms.FileInput(attrs={"class": "form-control-file"}))


class ImportCOAForm(forms.Form):
    excel_file = forms.FileField(widget=forms.FileInput(attrs={"class": "form-control-file"}))


class LoanReportFilterForm(forms.Form):
    start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    end_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": "form-control form-control-sm", "type": "date"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[("", "All statuses")] + Loan.STATUS_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    loan_product = forms.ChoiceField(
        required=False,
        choices=[("", "All products")] + Loan.LOAN_PURPOSE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    client = forms.ModelChoiceField(
        required=False,
        queryset=Client.objects.none(),
        empty_label="All clients",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    loan_officer = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.none(),
        empty_label="All officers",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    q = forms.CharField(
        required=False,
        label="Search",
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-sm",
                "placeholder": "Client, loan no., officer",
            }
        ),
    )
    per_page = forms.ChoiceField(
        required=False,
        choices=[("25", "25"), ("50", "50"), ("100", "100"), ("200", "200")],
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.filter(loans__isnull=False).distinct().order_by("full_name")
        self.fields["loan_officer"].queryset = (
            User.objects.filter(applied_loans__isnull=False).distinct().order_by("username")
        )

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            raise forms.ValidationError("End date cannot be before start date.")
        return cleaned_data


# ─────────────────────────────────────────────────────────────────────────────
# ChartOfAccountsForm
# ─────────────────────────────────────────────────────────────────────────────


class ChartOfAccountsForm(forms.ModelForm):
    class Meta:
        model = ChartOfAccounts
        fields = ["account_name", "account_type", "account_number", "description"]
        widgets = {
            "account_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account Name"}),
            "account_type": forms.Select(attrs={"class": "form-control"}),
            "account_number": forms.TextInput(attrs={"class": "form-control", "placeholder": "Account Number"}),
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": "Description (optional)"}),
        }

    def clean_account_number(self):
        value = self.cleaned_data.get("account_number", "")
        if len(value) < 3:
            raise forms.ValidationError("Account number must be at least 3 characters.")
        return value

    def clean_account_name(self):
        value = self.cleaned_data.get("account_name", "")
        if len(value) < 3:
            raise forms.ValidationError("Account name must be at least 3 characters.")
        return value


# ─────────────────────────────────────────────────────────────────────────────
# LoanApplicationForm
# ─────────────────────────────────────────────────────────────────────────────


class LoanApplicationForm(forms.ModelForm):
    """
    Used for new loan applications.  Fields managed by the system
    (borrower, account, dates, status, totals, approval chain) are excluded.
    """

    client = forms.ModelChoiceField(
        queryset=Client.objects.none(),
        label="Client / Member",
        empty_label="Select client",
        widget=forms.HiddenInput(),
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["client"].queryset = Client.objects.order_by("full_name", "reg_number")
        if self.instance and self.instance.pk and self.instance.borrower_id:
            self.fields["client"].initial = self.instance.borrower_id
        self.fields["start_date"].initial = self.fields["start_date"].initial or timezone.localdate()
        for field_name, field in self.fields.items():
            field.widget.attrs.setdefault("class", "form-control")
            field.widget.attrs.setdefault("autocomplete", "off")
        self.fields["client"].widget.attrs["id"] = "id_client"

    class Meta:
        model = Loan
        # Exclude all system-managed and approval-chain fields.
        # last_reminder_sent is also excluded — it is set by the notification command.
        exclude = (
            "borrower",
            "account",
            "disbursement_date",
            "due_date",
            "status",
            "interest_method",
            "total_interest",
            "approved_by_boo",
            "approved_by_hof",
            "approved_by_ed",
            "approved_date",
            "reason_for_rejection",
            "applied_by",
            "applied_by_role",
            "created_by",
            "created_at",
            "updated_at",
            "last_reminder_sent",
        )
        widgets = {
            "principal_amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "0.00",
                    "min": "1",
                    "step": "0.01",
                }
            ),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "interest_rate": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "0.00",
                    "min": "0",
                    "max": "30",
                    "step": "0.01",
                }
            ),
            "loan_period_months": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Months",
                    "min": "1",
                }
            ),
            "loan_purpose": forms.Select(attrs={"class": "form-select"}),
            "reason_for_approval": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Assessment notes for the approval workflow",
                    "rows": 3,
                }
            ),
        }

    def clean_principal_amount(self):
        principal = self.cleaned_data.get("principal_amount")
        if principal is not None and principal <= 0:
            raise forms.ValidationError("Principal amount must be greater than zero.")
        return principal

    def clean_loan_period_months(self):
        months = self.cleaned_data.get("loan_period_months")
        if months is not None and months < 1:
            raise forms.ValidationError("Loan period must be at least one month.")
        return months

    def clean_start_date(self):
        start_date = self.cleaned_data.get("start_date")
        if start_date and start_date > timezone.localdate():
            raise forms.ValidationError("Application date cannot be in the future.")
        return start_date

    def clean(self):
        cleaned_data = super().clean()
        client = cleaned_data.get("client")
        if client:
            active_loans = Loan.objects.filter(
                borrower=client,
                status__in=Loan.ACTIVE_STATUSES,
            ).prefetch_related("repayments", "penalties")
            if self.instance and self.instance.pk:
                active_loans = active_loans.exclude(pk=self.instance.pk)
            has_balance = any(loan.outstanding_balance() > 0 for loan in active_loans)
            if has_balance:
                raise forms.ValidationError(
                    f"{client.full_name} already has an active loan with an outstanding balance."
                )
        return cleaned_data

    def save(self, commit=True, user=None):
        loan = super().save(commit=False)
        loan.borrower = self.cleaned_data["client"]
        if user:
            loan.created_by = user
        if commit:
            loan.save()
        return loan


class ClientSelfServiceLoanApplicationForm(forms.ModelForm):
    """Borrower-facing loan application form."""

    application_notes = forms.CharField(
        label="Loan purpose / notes",
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "placeholder": "Briefly describe why you need this loan",
                "rows": 3,
            }
        ),
    )

    class Meta:
        model = Loan
        fields = [
            "principal_amount",
            "loan_purpose",
            "loan_period_months",
            "start_date",
            "application_notes",
        ]
        widgets = {
            "principal_amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "0.00",
                    "min": "1",
                    "step": "0.01",
                }
            ),
            "loan_purpose": forms.Select(attrs={"class": "form-select"}),
            "loan_period_months": forms.NumberInput(
                attrs={"class": "form-control", "placeholder": "Months", "min": "1"}
            ),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["start_date"].initial = self.fields["start_date"].initial or timezone.localdate()
        for field in self.fields.values():
            field.widget.attrs.setdefault("autocomplete", "off")

    def clean_principal_amount(self):
        principal = self.cleaned_data.get("principal_amount")
        if principal is not None and principal <= 0:
            raise forms.ValidationError("Principal amount must be greater than zero.")
        return principal

    def clean_loan_period_months(self):
        months = self.cleaned_data.get("loan_period_months")
        if months is not None and months < 1:
            raise forms.ValidationError("Loan period must be at least one month.")
        return months

    def clean_start_date(self):
        start_date = self.cleaned_data.get("start_date")
        if start_date and start_date > timezone.localdate():
            raise forms.ValidationError("Application date cannot be in the future.")
        return start_date

    def save(self, commit=True, borrower=None, user=None):
        loan = super().save(commit=False)
        if borrower is not None:
            loan.borrower = borrower
        loan.status = "pending"
        loan.interest_rate = getattr(settings, "SELF_SERVICE_LOAN_INTEREST_RATE", Decimal("0.00"))
        loan.reason_for_approval = self.cleaned_data.get("application_notes") or (
            "Self-service application submitted by the client."
        )
        if user is not None:
            loan.applied_by = user
            loan.applied_by_role = getattr(getattr(user, "profile", None), "role", "guest")
            loan.created_by = user
        if commit:
            loan.save()
        return loan


class LoanApplicationDocumentForm(forms.Form):
    national_id = forms.FileField(
        label="National ID",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"}),
    )
    collateral_security = forms.FileField(
        label="Collateral / security document",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"}),
    )
    proof_of_income = forms.FileField(
        label="Proof of income",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"}),
    )
    guarantor_form = forms.FileField(
        label="Guarantor form",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"}),
    )
    bank_statement = forms.FileField(
        label="Bank statement",
        required=True,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"}),
    )
    other = forms.FileField(
        label="Other document",
        required=False,
        widget=forms.ClearableFileInput(attrs={"class": "form-control", "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx"}),
    )
    other_description = forms.CharField(
        label="Other document description",
        required=False,
        max_length=255,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Describe the other document",
            }
        ),
    )

    document_fields = [
        "national_id",
        "collateral_security",
        "proof_of_income",
        "guarantor_form",
        "bank_statement",
        "other",
    ]

    def _clean_upload_extension(self, field_name):
        upload = self.cleaned_data.get(field_name)
        if not upload:
            return upload
        extension = os.path.splitext(upload.name)[1].lstrip(".").lower()
        if extension not in LOAN_DOCUMENT_ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Upload PDF, JPG, JPEG, PNG, DOC, or DOCX files.")
        return upload

    def clean_national_id(self):
        return self._clean_upload_extension("national_id")

    def clean_collateral_security(self):
        return self._clean_upload_extension("collateral_security")

    def clean_proof_of_income(self):
        return self._clean_upload_extension("proof_of_income")

    def clean_guarantor_form(self):
        return self._clean_upload_extension("guarantor_form")

    def clean_bank_statement(self):
        return self._clean_upload_extension("bank_statement")

    def clean_other(self):
        return self._clean_upload_extension("other")

    def clean(self):
        cleaned_data = super().clean()
        other = cleaned_data.get("other")
        other_description = cleaned_data.get("other_description")
        if other and not other_description:
            self.add_error("other_description", "Describe the other document.")
        return cleaned_data

    def save(self, loan, uploaded_by=None):
        documents = []
        for field_name in self.document_fields:
            upload = self.cleaned_data.get(field_name)
            if not upload:
                continue
            description = self.fields[field_name].label
            if field_name == "other":
                description = self.cleaned_data.get("other_description") or description
            documents.append(
                LoanApplicationDocument.objects.create(
                    loan=loan,
                    document_type=field_name,
                    file=upload,
                    description=description,
                    uploaded_by=uploaded_by,
                )
            )
        return documents


# ─────────────────────────────────────────────────────────────────────────────
# LoanApplicationUpdateForm
# ─────────────────────────────────────────────────────────────────────────────


class StaffLoanApplicationDocumentForm(forms.ModelForm):
    file = forms.FileField(
        label="PDF document",
        widget=forms.ClearableFileInput(
            attrs={
                "accept": ".pdf,application/pdf",
                "class": "form-control",
            }
        ),
    )

    class Meta:
        model = LoanApplicationDocument
        fields = ["document_type", "file", "description"]
        widgets = {
            "document_type": forms.Select(attrs={"class": "form-control"}),
            "description": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Optional note, reference, or source",
                }
            ),
        }

    def clean_file(self):
        upload = self.cleaned_data.get("file")
        if not upload:
            return upload

        extension = os.path.splitext(upload.name)[1].lstrip(".").lower()
        content_type = getattr(upload, "content_type", "")
        if extension != "pdf" or content_type not in {
            "application/pdf",
            "application/x-pdf",
            "",
        }:
            raise forms.ValidationError("Only PDF documents are allowed.")

        max_size = 10 * 1024 * 1024
        if upload.size > max_size:
            raise forms.ValidationError("PDF documents must not be larger than 10 MB.")

        return upload

    def save(self, loan, uploaded_by=None, commit=True):
        document = super().save(commit=False)
        document.loan = loan
        document.uploaded_by = uploaded_by
        if commit:
            document.save()
        return document


class LoanApplicationUpdateForm(forms.ModelForm):
    """Used to edit an existing loan application (e.g. correct a mistake)."""

    class Meta:
        model = Loan
        fields = [
            "principal_amount",
            "interest_rate",
            "interest_method",
            "start_date",
            "loan_period_months",
            "reason_for_approval",
        ]
        widgets = {
            "principal_amount": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Principal amount",
                    "min": 0,
                }
            ),
            "interest_rate": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Interest rate (%)",
                    "min": 0,
                    "step": 0.01,
                }
            ),
            "interest_method": forms.Select(attrs={"class": "form-control"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "loan_period_months": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Loan period (months)",
                    "min": 1,
                }
            ),
            "reason_for_approval": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Reason for approval",
                    "rows": 3,
                }
            ),
        }

    def save(self, commit=True, user=None):
        loan = super().save(commit=False)
        if user:
            loan.created_by = user
        if commit:
            loan.save()
        return loan


# ─────────────────────────────────────────────────────────────────────────────
# LoanRejectionForm
# ─────────────────────────────────────────────────────────────────────────────


class LoanRejectionForm(forms.Form):
    reason_for_rejection = forms.CharField(
        max_length=255,
        widget=forms.Textarea(
            attrs={
                "class": "form-control",
                "placeholder": "Enter reason for rejection",
                "rows": 3,
            }
        ),
        label="Reason for Rejection",
    )


# ─────────────────────────────────────────────────────────────────────────────
# LoanDisbursementForm
# ─────────────────────────────────────────────────────────────────────────────


class LoanDisbursementForm(forms.ModelForm):
    """Single-loan disbursement form."""

    loan = forms.ModelChoiceField(
        queryset=Loan.objects.filter(status="approved"),
        required=True,
        label="Select Loan",
        widget=forms.Select(attrs={"class": "chzn-select"}),
    )
    account = forms.ModelChoiceField(
        queryset=ChartOfAccounts.objects.filter(
            account_type="asset",
            account_number__range=(MIN_ACCOUNT_NUMBER, MAX_ACCOUNT_NUMBER),
        ),
        label="Paying Account",
        required=True,
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    disbursement_date = forms.DateField(
        label="Disbursement Date",
        required=True,
        initial=timezone.now().date,  # callable — evaluated fresh each render
        widget=forms.DateInput(attrs={"class": "form-control", "type": "date"}),
    )

    class Meta:
        model = LoanDisbursement
        fields = ["loan", "account", "payment_method"]
        widgets = {
            "payment_method": forms.Select(attrs={"class": "form-control"}),
        }

    def _post_clean(self):
        # The view marks the loan disbursed immediately before saving this model.
        # Running LoanDisbursement.clean() here would reject the approved loan too early.
        return

    def clean(self):
        cleaned_data = super().clean()
        loan = cleaned_data.get("loan")
        disbursement_date = cleaned_data.get("disbursement_date")

        if loan and disbursement_date:
            # Disbursement date must not be before the loan application date
            if disbursement_date < loan.start_date:
                raise forms.ValidationError(
                    f"Disbursement date cannot be before the loan application date " f"({loan.start_date})."
                )
            if disbursement_date > timezone.localdate():
                raise forms.ValidationError("Disbursement date cannot be in the future.")
        return cleaned_data

    def save(self, commit=True):
        disbursement = LoanDisbursement(
            loan=self.cleaned_data["loan"],
            account=self.cleaned_data["account"],
            payment_method=self.cleaned_data["payment_method"],
        )
        if commit:
            disbursement.save()
        return disbursement


# ─────────────────────────────────────────────────────────────────────────────
# LoanAllDisbursementForm
# ─────────────────────────────────────────────────────────────────────────────


class LoanAllDisbursementForm(forms.ModelForm):
    """Bulk disbursement form — disburses all eligible approved loans at once."""

    account = forms.ModelChoiceField(
        queryset=ChartOfAccounts.objects.filter(
            account_type="asset",
            account_number__range=(MIN_ACCOUNT_NUMBER, MAX_ACCOUNT_NUMBER),
        ),
        label="Paying Account",
        required=True,
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = LoanDisbursement
        fields = ["account", "payment_method"]
        widgets = {
            "payment_method": forms.Select(attrs={"class": "form-control"}),
        }

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("account"):
            raise forms.ValidationError("A paying account must be selected.")
        if not cleaned_data.get("payment_method"):
            raise forms.ValidationError("A payment method must be selected.")
        return cleaned_data

    def save(self, approved_loans):
        """
        Disburse all eligible loans.
        Sets disbursement_date to today if not already set.
        Calls disbursement.save() which triggers _post_entries() in the model.
        """
        disbursed_count = 0
        today = timezone.now().date()

        with transaction.atomic():
            for loan in approved_loans:
                loan.disburse(today)

                LoanDisbursement.objects.create(
                    loan=loan,
                    account=self.cleaned_data["account"],
                    payment_method=self.cleaned_data["payment_method"],
                )  # model save() triggers _post_entries()

                disbursed_count += 1

        return disbursed_count


# ─────────────────────────────────────────────────────────────────────────────
# Shared queryset helper for loan dropdowns
# ─────────────────────────────────────────────────────────────────────────────


def active_loans_with_balance_queryset():
    """
    Returns loans with status disbursed/overdue that still have an
    outstanding balance, annotated for dropdown display.

    Uses isolated subqueries for each related balance so repayment rows are not
    multiplied by penalty rows when a loan has penalty history.
    """
    money_field = DecimalField(max_digits=15, decimal_places=2)
    zero = Value(Decimal("0.00"), output_field=money_field)
    principal_paid = (
        LoanRepayment.objects.filter(loan=OuterRef("pk"))
        .values("loan")
        .annotate(total=Sum("principal_payment"))
        .values("total")[:1]
    )
    interest_paid = (
        LoanRepayment.objects.filter(loan=OuterRef("pk"))
        .values("loan")
        .annotate(total=Sum("interest_payment"))
        .values("total")[:1]
    )
    unpaid_penalties = (
        LoanPenalty.objects.filter(
            loan=OuterRef("pk"),
            is_paid=False,
            is_deleted=False,
        )
        .values("loan")
        .annotate(total=Sum("remaining_amount"))
        .values("total")[:1]
    )

    return (
        Loan.objects.annotate(
            paid_principal=Coalesce(Subquery(principal_paid), zero),
            paid_interest=Coalesce(Subquery(interest_paid), zero),
            remaining_penalty=Coalesce(Subquery(unpaid_penalties), zero),
        )
        .annotate(
            remaining_principal=F("principal_amount") - F("paid_principal"),
            remaining_interest=Coalesce(F("total_interest"), zero) - F("paid_interest"),
        )
        .filter(
            Q(remaining_principal__gt=0) | Q(remaining_interest__gt=0) | Q(remaining_penalty__gt=0),
            status__in=["disbursed", "overdue"],
        )
        .distinct()
        .select_related("borrower")
        .order_by("borrower__full_name", "id")
    )


def _active_loans_with_balance():
    return active_loans_with_balance_queryset()


# ─────────────────────────────────────────────────────────────────────────────
# LoanRepaymentForm
# ─────────────────────────────────────────────────────────────────────────────


class LoanRepaymentForm(forms.ModelForm):
    """
    Changes vs original:
    • Loan queryset uses shared _active_loans_with_balance() helper.
    • clean() validates against calculate_remaining_balances() (model method)
      which is the single source of truth — consistent with LoanRepayment.clean().
    • Removed the "penalty must exactly equal remaining" rule — partial penalty
      payments are valid (model supports them via _mark_penalties_paid).
    • Added zero-payment guard: at least one payment field must be > 0.
    """

    loan = forms.ModelChoiceField(
        queryset=Loan.objects.none(),  # populated in __init__
        label="Loan",
        widget=forms.Select(attrs={"class": "chzn-select"}),
    )
    account = forms.ModelChoiceField(
        queryset=ChartOfAccounts.objects.filter(
            account_type="asset",
            account_number__range=(MIN_ACCOUNT_NUMBER, MAX_ACCOUNT_NUMBER),
        ),
        label="Paying Account",
        widget=forms.Select(attrs={"class": "form-control"}),
    )
    principal_payment = forms.DecimalField(
        label="Principal Payment",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=15,
        initial=Decimal("0.00"),
        required=False,
    )
    interest_payment = forms.DecimalField(
        label="Interest Payment",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=15,
        initial=Decimal("0.00"),
        required=False,
    )
    penalty_payment = forms.DecimalField(
        label="Penalty Payment",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        min_value=Decimal("0"),
        decimal_places=2,
        max_digits=15,
        initial=Decimal("0.00"),
        required=False,
    )

    class Meta:
        model = LoanRepayment
        fields = [
            "loan",
            "repayment_date",
            "principal_payment",
            "interest_payment",
            "penalty_payment",
            "account",
        ]
        widgets = {
            "repayment_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        loan_queryset = kwargs.pop("loan_queryset", None)
        super().__init__(*args, **kwargs)
        self.fields["loan"].queryset = (
            loan_queryset if loan_queryset is not None else active_loans_with_balance_queryset()
        )

    def clean(self):
        cleaned_data = super().clean()
        loan = cleaned_data.get("loan")
        principal_payment = cleaned_data.get("principal_payment") or Decimal("0.00")
        interest_payment = cleaned_data.get("interest_payment") or Decimal("0.00")
        penalty_payment = cleaned_data.get("penalty_payment") or Decimal("0.00")

        if not loan:
            raise forms.ValidationError("Please select a loan.")

        repayment_date = cleaned_data.get("repayment_date")
        if repayment_date and repayment_date > timezone.localdate():
            self.add_error("repayment_date", "Repayment date cannot be in the future.")
        if repayment_date and loan.disbursement_date and repayment_date < loan.disbursement_date:
            self.add_error(
                "repayment_date",
                "Repayment date cannot be before the loan disbursement date.",
            )

        # Guard: at least one field must be non-zero
        if principal_payment + interest_payment + penalty_payment <= 0:
            raise forms.ValidationError(
                "At least one payment field (principal, interest, or penalty) must be greater than zero."
            )

        # Use model method — single source of truth, consistent with LoanRepayment.clean()
        balances = loan.calculate_remaining_balances()

        if principal_payment > balances["principal_balance"]:
            self.add_error(
                "principal_payment",
                f"Cannot exceed remaining principal balance of " f"{balances['principal_balance']:,.2f}.",
            )
        if interest_payment > balances["interest_balance"]:
            self.add_error(
                "interest_payment",
                f"Cannot exceed remaining interest balance of " f"{balances['interest_balance']:,.2f}.",
            )
        if penalty_payment > balances["penalty_balance"]:
            self.add_error(
                "penalty_payment",
                f"Cannot exceed remaining penalty balance of " f"{balances['penalty_balance']:,.2f}.",
            )

        return cleaned_data


# ─────────────────────────────────────────────────────────────────────────────
# LoanPenaltyForm
# ─────────────────────────────────────────────────────────────────────────────


class LoanPenaltyForm(forms.ModelForm):
    """
    Changes vs original:
    • Loan queryset uses shared _active_loans_with_balance() helper.
    • account queryset uses get_or_none pattern with a clear fallback message
      instead of silently falling back to all disbursed/overdue loans.
    • output_field in annotations uses DecimalField() from django.db.models
      (not forms.DecimalField) — fixes the original type mismatch.
    """

    loan = forms.ModelChoiceField(
        queryset=Loan.objects.none(),  # populated in __init__
        label="Loan",
        widget=forms.Select(attrs={"class": "chzn-select"}),
    )
    penalty_amount = forms.DecimalField(
        label="Penalty Amount",
        widget=forms.NumberInput(attrs={"class": "form-control"}),
        min_value=Decimal("0.01"),
        decimal_places=2,
        max_digits=15,
    )
    penalty_date = forms.DateField(
        label="Penalty Date",
        initial=timezone.now().date,  # callable — evaluated fresh each render
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
    )
    reason = forms.CharField(
        label="Penalty Reason",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    account = forms.ModelChoiceField(
        queryset=ChartOfAccounts.objects.filter(account_number="1071"),
        label="Penalty Account",
        widget=forms.Select(attrs={"class": "form-control"}),
    )

    class Meta:
        model = LoanPenalty
        fields = ["loan", "penalty_date", "penalty_amount", "reason", "account"]

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        loan_queryset = kwargs.pop("loan_queryset", None)
        super().__init__(*args, **kwargs)

        # Loan dropdown — loans with outstanding balances
        self.fields["loan"].queryset = (
            loan_queryset if loan_queryset is not None else active_loans_with_balance_queryset()
        )

        # Pre-select the penalty receivable account (1071) if it exists
        try:
            self.fields["account"].initial = ChartOfAccounts.objects.get(account_number="1071")
        except ChartOfAccounts.DoesNotExist:
            logger.warning("Penalty account 1071 not found — " "please create it in Chart of Accounts.")

        if user:
            self.instance.created_by = user

    def clean_penalty_amount(self):
        amount = self.cleaned_data.get("penalty_amount")
        if amount is not None and amount <= 0:
            raise forms.ValidationError("Penalty amount must be positive.")
        return amount

    def clean_penalty_date(self):
        penalty_date = self.cleaned_data.get("penalty_date")
        if penalty_date and penalty_date > timezone.now().date():
            raise forms.ValidationError("Penalty date cannot be in the future.")
        loan = self.cleaned_data.get("loan")
        if penalty_date and loan and loan.disbursement_date and penalty_date < loan.disbursement_date:
            raise forms.ValidationError("Penalty date cannot be before the loan disbursement date.")
        return penalty_date
