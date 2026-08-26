from decimal import Decimal

from rest_framework import serializers

from apps.loans.models import Loan, LoanApplicationDocument
from .media import absolute_media_url


class LoanApplicationDocumentSerializer(serializers.ModelSerializer):
    document_type_label = serializers.CharField(source="get_document_type_display", read_only=True)
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplicationDocument
        fields = (
            "id",
            "loan",
            "document_type",
            "document_type_label",
            "description",
            "file_url",
            "created_at",
        )
        read_only_fields = fields

    def get_file_url(self, obj):
        return absolute_media_url(self, obj.file)


class LoanApplicationSerializer(serializers.Serializer):
    borrower = serializers.IntegerField(required=False)
    principal_amount = serializers.DecimalField(max_digits=15, decimal_places=2)
    loan_purpose = serializers.ChoiceField(choices=Loan.LOAN_PURPOSE_CHOICES)
    loan_period_months = serializers.IntegerField(min_value=1)
    start_date = serializers.DateField(required=False)
    interest_rate = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, min_value=0, max_value=30)
    reason_for_approval = serializers.CharField(required=False, allow_blank=True, max_length=255)


class LoanActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    disbursement_date = serializers.DateField(required=False)


class LoanSerializer(serializers.ModelSerializer):
    borrower_name = serializers.CharField(source="borrower.full_name", read_only=True)
    borrower_reg_number = serializers.CharField(source="borrower.reg_number", read_only=True)
    monthly_installment = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_repayable = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)
    total_outstanding = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()
    missing_required_documents = serializers.SerializerMethodField()
    can_approve = serializers.SerializerMethodField()
    can_reject = serializers.SerializerMethodField()
    can_update = serializers.SerializerMethodField()
    can_delete = serializers.SerializerMethodField()
    can_disburse = serializers.SerializerMethodField()

    class Meta:
        model = Loan
        fields = (
            "id",
            "borrower",
            "borrower_name",
            "borrower_reg_number",
            "principal_amount",
            "interest_rate",
            "total_interest",
            "total_repayable",
            "monthly_installment",
            "total_outstanding",
            "loan_period_months",
            "start_date",
            "disbursement_date",
            "due_date",
            "status",
            "loan_purpose",
            "reason_for_rejection",
            "reason_for_approval",
            "documents",
            "missing_required_documents",
            "can_approve",
            "can_reject",
            "can_update",
            "can_delete",
            "can_disburse",
        )

    def get_total_outstanding(self, obj):
        repayments = list(obj.repayments.all())
        penalties = list(obj.penalties.all())
        paid_principal = sum((item.principal_payment or Decimal("0")) for item in repayments)
        paid_interest = sum((item.interest_payment or Decimal("0")) for item in repayments)
        unpaid_penalties = sum(
            (item.remaining_amount or Decimal("0"))
            for item in penalties
            if not item.is_paid and not item.is_deleted
        )
        return (
            max(obj.principal_amount - paid_principal, Decimal("0"))
            + max((obj.total_interest or Decimal("0")) - paid_interest, Decimal("0"))
            + max(unpaid_penalties, Decimal("0"))
        )

    def get_documents(self, obj):
        return LoanApplicationDocumentSerializer(obj.documents.all(), many=True, context=self.context).data

    def get_missing_required_documents(self, obj):
        attached_types = {
            document.document_type
            for document in obj.documents.all()
            if document.file and document.document_type in obj.REQUIRED_DOCUMENT_TYPES
        }
        labels = dict(LoanApplicationDocument.DOCUMENT_TYPE_CHOICES)
        return [
            {"type": item, "label": labels.get(item, item.replace("_", " ").title())}
            for item in obj.REQUIRED_DOCUMENT_TYPES
            if item not in attached_types
        ]

    def get_can_approve(self, obj):
        return can_approve_loan(self.context.get("request"), obj)

    def get_can_reject(self, obj):
        return can_reject_loan(self.context.get("request"), obj)

    def get_can_update(self, obj):
        return can_update_loan(self.context.get("request"), obj)

    def get_can_delete(self, obj):
        return can_delete_loan(self.context.get("request"), obj)

    def get_can_disburse(self, obj):
        return is_mobile_admin_or_manager(self.context.get("request")) and obj.status == "approved"


def mobile_user_role(request):
    if not request or not getattr(request, "user", None):
        return ""
    profile = getattr(request.user, "profile", None)
    return (
        getattr(profile, "resolved_staff_role", "")
        or getattr(profile, "staff_role", "")
        or getattr(profile, "role", "")
    )


def is_mobile_internal_user(request):
    role = mobile_user_role(request)
    profile = getattr(getattr(request, "user", None), "profile", None)
    return bool(
        role in {"administrator", "manager", "staff", "boo", "hof", "ed", "accountant"}
        or getattr(profile, "resolved_account_type", "") == "staff"
        or getattr(getattr(request, "user", None), "is_staff", False)
        or getattr(getattr(request, "user", None), "is_superuser", False)
    )


def is_mobile_admin_or_manager(request):
    return mobile_user_role(request) in {"administrator", "manager"} or getattr(getattr(request, "user", None), "is_superuser", False)


def owns_mobile_loan(request, loan):
    profile = getattr(getattr(request, "user", None), "profile", None)
    return bool(getattr(profile, "client_id", None) and profile.client_id == loan.borrower_id)


def can_approve_loan(request, loan):
    return (loan.status, mobile_user_role(request)) in Loan.APPROVAL_TRANSITIONS


def can_reject_loan(request, loan):
    if loan.status not in {"pending", "boo_approved", "hof_approved"}:
        return False
    if is_mobile_admin_or_manager(request):
        return True
    return can_approve_loan(request, loan)


def can_update_loan(request, loan):
    if is_mobile_admin_or_manager(request):
        return loan.status not in {"disbursed", "closed", "repaid"}
    if is_mobile_internal_user(request):
        return loan.status in {"pending", "boo_approved", "hof_approved"}
    return owns_mobile_loan(request, loan) and loan.status == "pending"


def can_delete_loan(request, loan):
    return is_mobile_admin_or_manager(request) and loan.status not in {"disbursed", "closed", "repaid"}
