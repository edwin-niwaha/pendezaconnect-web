from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from api.v1.selectors import (
    clients_for_user,
    linked_client_id,
    loans_for_user,
    savings_accounts_for_client,
    savings_transactions_for_client,
)
from api.v1.serializers import (
    ClientSerializer,
    LoanSerializer,
    SavingsAccountSerializer,
    SavingsRequestSerializer,
    SavingsTransactionSerializer,
)
from apps.savings.models import SavingsAccount, SavingsTransaction
from apps.users.tasks import queue_user_notification


class ClientViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["full_name", "reg_number", "email"]
    ordering_fields = ["id", "full_name", "reg_number"]
    ordering = ["id"]

    def get_queryset(self):
        queryset = clients_for_user(self.request.user)
        selected_view = self.request.query_params.get("view", "all")
        if selected_view == "active_loans":
            queryset = queryset.filter(active_loans_count__gt=0)
        elif selected_view == "has_savings":
            queryset = queryset.filter(calculated_savings_balance__gt=0)
        return queryset

    @action(detail=True, methods=["post", "delete"], parser_classes=[MultiPartParser, FormParser])
    def photos(self, request, pk=None):
        client = self.get_object()

        if request.method == "DELETE":
            client.picture = None
            client.save(update_fields=["picture", "updated_at"])
            return Response(self.get_serializer(client).data, status=status.HTTP_200_OK)

        picture = request.FILES.get("picture")
        if not picture:
            return Response({"picture": ["No image file was submitted."]}, status=status.HTTP_400_BAD_REQUEST)

        client.picture = picture
        client.save(update_fields=["picture", "updated_at"])
        return Response(self.get_serializer(client).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def loans(self, request, pk=None):
        client = self.get_object()
        loans = loans_for_user(request.user).filter(borrower=client)
        return Response(LoanSerializer(loans, many=True).data)

    @action(detail=True, methods=["get"])
    def savings(self, request, pk=None):
        client = self.get_object()
        return Response(
            {
                "accounts": SavingsAccountSerializer(
                    savings_accounts_for_client(client), many=True
                ).data,
                "transactions": SavingsTransactionSerializer(
                    savings_transactions_for_client(client)[:30], many=True
                ).data,
            }
        )

    @action(detail=True, methods=["post"], url_path="savings/requests")
    def savings_requests(self, request, pk=None):
        client = self.get_object()
        if linked_client_id(request.user) != client.id:
            return Response(
                {"detail": "Only the linked client can submit a savings request."},
                status=status.HTTP_403_FORBIDDEN,
            )
        account = SavingsAccount.objects.filter(client=client, status="active").first()
        if account is None:
            return Response(
                {"detail": "No active savings account is linked to this client."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SavingsRequestSerializer(
            data=request.data, context={"account": account}
        )
        serializer.is_valid(raise_exception=True)
        savings_request = SavingsTransaction.objects.create(
            account=account,
            requested_by=request.user,
            status="pending",
            **serializer.validated_data,
        )
        queue_user_notification([request.user.id], "savings_request_submitted", savings_request.id)
        return Response(
            {
                "detail": "Savings request submitted for review.",
                "request": SavingsTransactionSerializer(savings_request).data,
            },
            status=status.HTTP_201_CREATED,
        )
