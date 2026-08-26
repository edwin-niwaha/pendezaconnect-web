from rest_framework import filters, permissions, viewsets
import re

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from api.v1.selectors import payments_for_user
from api.v1.serializers import PaymentSerializer
from apps.sponsorship.models import MoMoTransaction
from apps.sponsorship.momo_prod import create_access_token, generate_uuid, request_to_pay
from api.v1.throttles import PaymentStartThrottle, PaymentStatusThrottle


class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["sponsor__first_name", "sponsor__last_name", "program__name"]
    ordering_fields = ["payment_date", "amount", "id"]
    ordering = ["-payment_date", "-id"]

    def get_queryset(self):
        return payments_for_user(self.request.user)

    @action(detail=False, methods=["get"])
    def recent(self, request):
        payments = self.get_queryset()[:25]
        return Response(PaymentSerializer(payments, many=True).data)

    @action(
        detail=False,
        methods=["post"],
        authentication_classes=[],
        permission_classes=[permissions.AllowAny],
        throttle_classes=[PaymentStartThrottle],
        url_path="mobile-money/initiate",
    )
    def initiate_mobile_money(self, request):
        phone = str(request.data.get("phone", "")).strip().replace(" ", "")
        name = str(request.data.get("name", "")).strip() or None
        email = str(request.data.get("email", "")).strip() or None
        if not re.fullmatch(r"07\d{8}", phone):
            return Response({"phone": ["Enter a valid MTN number in the format 07XXXXXXXX."]}, status=status.HTTP_400_BAD_REQUEST)

        try:
            amount = int(str(request.data.get("amount", "")).replace(",", ""))
        except (TypeError, ValueError):
            amount = 0
        if amount < 5000:
            return Response({"amount": ["Amount must be at least UGX 5,000."]}, status=status.HTTP_400_BAD_REQUEST)

        token = create_access_token(settings.MOMO_API_USER, settings.MOMO_API_KEY, settings.SUBSCRIPTION_KEY)
        if not token:
            return Response({"detail": "Mobile Money is temporarily unavailable. Please try again."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        reference_id = generate_uuid()
        transaction = MoMoTransaction.objects.create(
            reference_id=reference_id,
            external_id=reference_id,
            phone_number=phone,
            amount=amount,
            currency="UGX",
            status="PENDING",
            donor_name=name,
            donor_email=email,
            payer_message="Pendeza Uganda Donation",
            payee_note="Thank you for supporting Pendeza Uganda",
        )
        provider_status, _ = request_to_pay(token, settings.SUBSCRIPTION_KEY, "256" + phone[1:], amount, reference_id)
        if provider_status != 202:
            transaction.status = "FAILED"
            transaction.save(update_fields=["status", "updated_at"])
            return Response({"detail": "MTN could not send the payment prompt. Please try again."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response({
            "reference_id": reference_id,
            "status": "PENDING",
            "amount": amount,
            "currency": "UGX",
            "phone": phone,
            "message": "Prompt sent. Approve the request on your phone.",
        }, status=status.HTTP_202_ACCEPTED)

    @action(
        detail=False,
        methods=["get"],
        authentication_classes=[],
        permission_classes=[permissions.AllowAny],
        throttle_classes=[PaymentStatusThrottle],
        url_path=r"mobile-money/(?P<reference_id>[0-9a-f-]+)/status",
    )
    def mobile_money_status(self, request, reference_id=None):
        try:
            transaction = MoMoTransaction.objects.get(reference_id=reference_id)
        except MoMoTransaction.DoesNotExist:
            return Response({"detail": "Transaction not found."}, status=status.HTTP_404_NOT_FOUND)

        if transaction.status == "PENDING":
            token = create_access_token(settings.MOMO_API_USER, settings.MOMO_API_KEY, settings.SUBSCRIPTION_KEY)
            if token:
                url = f"https://proxy.momoapi.mtn.com/collection/v1_0/requesttopay/{reference_id}"
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Ocp-Apim-Subscription-Key": settings.SUBSCRIPTION_KEY,
                    "X-Target-Environment": "mtnuganda",
                }
                try:
                    provider_response = requests.get(url, headers=headers, timeout=30)
                    if provider_response.status_code == 200:
                        provider_data = provider_response.json()
                        provider_state = provider_data.get("status", "PENDING")
                        if provider_state in {"PENDING", "SUCCESSFUL", "FAILED"}:
                            transaction.status = provider_state
                            failure_reason = provider_data.get("reason") if provider_state == "FAILED" else None
                            transaction.payer_message = failure_reason or provider_data.get("payerMessage") or transaction.payer_message
                            transaction.payee_note = provider_data.get("payeeNote") or transaction.payee_note
                            transaction.save(update_fields=["status", "payer_message", "payee_note", "updated_at"])
                except (requests.RequestException, ValueError):
                    pass

        return Response({
            "reference_id": transaction.reference_id,
            "status": transaction.status,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "phone": f"******{str(transaction.phone_number)[-4:]}",
            "reason": transaction.payer_message if transaction.status == "FAILED" else "",
            "updated_at": transaction.updated_at,
        })
