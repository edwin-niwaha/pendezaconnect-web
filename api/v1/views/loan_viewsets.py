from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from api.v1.selectors import is_internal_user, linked_client_id, loans_for_user
from api.v1.serializers import (
    LoanActionSerializer,
    LoanApplicationDocumentSerializer,
    LoanApplicationSerializer,
    LoanSerializer,
)
from api.v1.serializers.loan_serializers import (
    can_delete_loan,
    can_reject_loan,
    can_update_loan,
    is_mobile_admin_or_manager,
    is_mobile_internal_user,
)
from apps.client.models import Client
from apps.loans.models import Loan, LoanApplicationDocument
from apps.users.models import Profile
from apps.users.tasks import queue_user_notification
from api.v1.uploads import validate_document_upload


class LoanViewSet(viewsets.ModelViewSet):
    serializer_class = LoanSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["borrower__full_name", "borrower__reg_number", "status"]
    ordering_fields = ["id", "start_date", "due_date", "principal_amount"]
    ordering = ["-id"]

    def get_queryset(self):
        queryset = loans_for_user(self.request.user).prefetch_related(
            "documents", "repayments", "penalties"
        )
        requested_statuses = {
            value.strip()
            for value in self.request.query_params.get("status", "").split(",")
            if value.strip()
        }
        valid_statuses = {value for value, _label in Loan.STATUS_CHOICES}
        selected_statuses = requested_statuses & valid_statuses
        if selected_statuses:
            queryset = queryset.filter(status__in=selected_statuses)
        return queryset

    def _serialize(self, loan, response_status=status.HTTP_200_OK):
        serializer = self.get_serializer(loan)
        return Response(serializer.data, status=response_status)

    def _notify_borrower(self, loan, event):
        user_ids = Profile.objects.filter(client_id=loan.borrower_id, user__is_active=True).values_list("user_id", flat=True)
        queue_user_notification(user_ids, event, loan.id)

    def _file_url(self, document):
        if not document.file:
            return None
        try:
            return document.file.url
        except ValueError:
            return str(document.file)

    def _document_description(self, document_type):
        return dict(LoanApplicationDocument.DOCUMENT_TYPE_CHOICES).get(
            document_type,
            document_type.replace("_", " ").title(),
        )

    def _save_documents(self, loan, files):
        documents = []
        valid_types = {choice[0] for choice in LoanApplicationDocument.DOCUMENT_TYPE_CHOICES}
        for document_type in valid_types:
            upload = files.get(document_type)
            if not upload:
                continue
            upload = validate_document_upload(upload, document_type)
            documents.append(
                LoanApplicationDocument.objects.create(
                    loan=loan,
                    document_type=document_type,
                    file=upload,
                    description=self._document_description(document_type),
                    uploaded_by=self.request.user,
                )
            )
        return documents

    def create(self, request, *args, **kwargs):
        serializer = LoanApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if is_mobile_internal_user(request):
            borrower_id = data.get("borrower")
            if not borrower_id:
                return Response({"borrower": ["This field is required for staff-created applications."]}, status=status.HTTP_400_BAD_REQUEST)
            borrower = Client.objects.filter(id=borrower_id).first()
            if not borrower:
                return Response({"borrower": ["Selected client was not found."]}, status=status.HTTP_400_BAD_REQUEST)
        else:
            client_id = linked_client_id(request.user)
            if not client_id:
                return Response({"detail": "Your login is not linked to a client record."}, status=status.HTTP_403_FORBIDDEN)
            borrower = Client.objects.get(id=client_id)
            blocking_statuses = {"pending", "boo_approved", "hof_approved", "approved", *Loan.ACTIVE_STATUSES}
            if Loan.objects.filter(borrower=borrower, status__in=blocking_statuses).exists():
                return Response({"detail": "You already have a pending application or running loan."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            loan = Loan.objects.create(
                borrower=borrower,
                principal_amount=data["principal_amount"],
                loan_purpose=data["loan_purpose"],
                loan_period_months=data["loan_period_months"],
                start_date=data.get("start_date") or timezone.localdate(),
                interest_rate=data.get("interest_rate") or getattr(settings, "SELF_SERVICE_LOAN_INTEREST_RATE", 0),
                reason_for_approval=data.get("reason_for_approval") or "Mobile loan application submitted.",
                applied_by=request.user,
                applied_by_role=getattr(getattr(request.user, "profile", None), "role", "guest"),
                created_by=request.user,
                status="pending",
            )
            self._save_documents(loan, request.FILES)

        self._notify_borrower(loan, "loan_submitted")
        return self._serialize(loan, status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        loan = self.get_object()
        if not can_update_loan(request, loan):
            return Response({"detail": "You do not have permission to update this loan."}, status=status.HTTP_403_FORBIDDEN)
        serializer = LoanApplicationSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        for field in ("principal_amount", "loan_purpose", "loan_period_months", "start_date", "interest_rate", "reason_for_approval"):
            if field in data:
                setattr(loan, field, data[field])
        if is_mobile_internal_user(request) and "borrower" in data:
            borrower = Client.objects.filter(id=data["borrower"]).first()
            if not borrower:
                return Response({"borrower": ["Selected client was not found."]}, status=status.HTTP_400_BAD_REQUEST)
            loan.borrower = borrower
        try:
            loan.save()
        except ValidationError as exc:
            return Response({"detail": exc.messages if hasattr(exc, "messages") else str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._serialize(loan)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        loan = self.get_object()
        if not can_delete_loan(request, loan):
            return Response({"detail": "You do not have permission to delete this loan."}, status=status.HTTP_403_FORBIDDEN)
        loan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["get"], url_path="approval-queue")
    def approval_queue(self, request):
        if not is_internal_user(request.user):
            return Response([], status=status.HTTP_200_OK)
        role = getattr(getattr(request.user, "profile", None), "resolved_staff_role", "") or getattr(getattr(request.user, "profile", None), "role", "")
        stage_map = {"boo": "pending", "hof": "boo_approved", "ed": "hof_approved"}
        statuses = [stage_map[role]] if role in stage_map else ["pending", "boo_approved", "hof_approved", "approved"]
        loans = self.get_queryset().filter(status__in=statuses)
        return Response(self.get_serializer(loans, many=True).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        loan = self.get_object()
        try:
            loan.approve(request.user)
        except ValidationError as exc:
            return Response({"detail": exc.messages if hasattr(exc, "messages") else str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        self._notify_borrower(loan, "loan_updated")
        return self._serialize(loan)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        loan = self.get_object()
        if not can_reject_loan(request, loan):
            return Response({"detail": "You do not have permission to reject this loan."}, status=status.HTTP_403_FORBIDDEN)
        serializer = LoanActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            loan.reject(serializer.validated_data.get("reason") or "Rejected from mobile review.")
        except ValidationError as exc:
            return Response({"detail": exc.messages if hasattr(exc, "messages") else str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        self._notify_borrower(loan, "loan_updated")
        return self._serialize(loan)

    @action(detail=True, methods=["post"])
    def disburse(self, request, pk=None):
        if not is_mobile_admin_or_manager(request):
            return Response({"detail": "Only administrators and managers can disburse loans."}, status=status.HTTP_403_FORBIDDEN)
        loan = self.get_object()
        serializer = LoanActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            loan.disburse(serializer.validated_data.get("disbursement_date") or timezone.localdate())
        except ValidationError as exc:
            return Response({"detail": exc.messages if hasattr(exc, "messages") else str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        loan.refresh_from_db()
        self._notify_borrower(loan, "loan_disbursed")
        return self._serialize(loan)

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def documents(self, request, pk=None):
        loan = self.get_object()
        if not can_update_loan(request, loan) and not (loan.status == "pending" and loan.borrower_id == linked_client_id(request.user)):
            return Response({"detail": "You do not have permission to upload documents for this loan."}, status=status.HTTP_403_FORBIDDEN)
        documents = self._save_documents(loan, request.FILES)
        if not documents:
            return Response({"detail": "No supported loan document file was submitted."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(LoanApplicationDocumentSerializer(documents, many=True).data, status=status.HTTP_201_CREATED)
