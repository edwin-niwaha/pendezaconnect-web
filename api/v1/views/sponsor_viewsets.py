from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.v1.selectors import (
    child_payments_for_sponsor,
    payments_for_user,
    sponsors_for_user,
    staff_payments_for_sponsor,
)
from api.v1.serializers import (
    ChildPaymentSerializer,
    PaymentSerializer,
    SponsorSerializer,
    StaffPaymentSerializer,
)


class SponsorViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SponsorSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["first_name", "last_name", "email"]
    ordering_fields = ["id", "first_name", "last_name"]
    ordering = ["id"]

    def get_queryset(self):
        queryset = sponsors_for_user(self.request.user)
        category_fields = {
            "child": "is_child_sponsor",
            "staff": "is_staff_sponsor",
            "family": "is_family_supporter",
            "general": "is_general_donor",
            "one_time": "is_one_time_donor",
        }
        category = self.request.query_params.get("category", "all")
        if category in category_fields:
            queryset = queryset.filter(**{category_fields[category]: True})
        return queryset

    @action(detail=True, methods=["get"])
    def payments(self, request, pk=None):
        sponsor = self.get_object()
        return Response(
            {
                "child_payments": ChildPaymentSerializer(child_payments_for_sponsor(sponsor)[:25], many=True).data,
                "staff_payments": StaffPaymentSerializer(staff_payments_for_sponsor(sponsor)[:25], many=True).data,
                "sponsor_payments": PaymentSerializer(
                    payments_for_user(request.user).filter(sponsor=sponsor)[:25], many=True
                ).data,
            }
        )
