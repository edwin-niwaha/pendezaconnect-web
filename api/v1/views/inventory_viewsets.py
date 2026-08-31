from django.db.models import F, Q
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from api.v1.permissions import IsInternalUser
from api.v1.serializers.inventory_serializers import InventoryProductSerializer, StockMovementSerializer
from apps.inventory.products.models import Product, StockMovement


class InventoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InventoryProductSerializer
    permission_classes = [IsInternalUser]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "description", "category__name", "supplier__name"]
    ordering_fields = ["name", "cost", "price", "updated_at"]
    ordering = ["name"]

    def get_queryset(self):
        return Product.objects.select_related("category", "supplier", "inventory").prefetch_related("variants").all()

    @action(detail=False, methods=["get"])
    def summary(self, request):
        products = self.get_queryset()
        low_stock = 0
        out_of_stock = 0
        for product in products:
            if product.stock_on_hand <= 0:
                out_of_stock += 1
            elif product.has_variants:
                low_stock += int(any(variant.is_low_stock for variant in product.active_variants))
            elif hasattr(product, "inventory") and product.inventory.is_low_stock:
                low_stock += 1
        return Response(
            {
                "products": products.count(),
                "active_products": products.filter(status="ACTIVE").count(),
                "total_stock": sum(product.stock_on_hand for product in products),
                "low_stock": low_stock,
                "out_of_stock": out_of_stock,
                "stock_value": sum(product.stock_on_hand * product.cost for product in products),
            }
        )

    @action(detail=False, methods=["get"], url_path="alerts")
    def alerts(self, request):
        products = (
            self.get_queryset()
            .filter(
                Q(inventory__quantity__lte=F("inventory__low_stock_threshold"))
                | Q(variants__quantity__lte=F("variants__low_stock_threshold"), variants__status="ACTIVE")
            )
            .distinct()
        )
        page = self.paginate_queryset(products)
        serializer = self.get_serializer(page if page is not None else products, many=True)
        return self.get_paginated_response(serializer.data) if page is not None else Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="movements")
    def movements(self, request):
        queryset = StockMovement.objects.select_related("product", "variant", "created_by").all()[:20]
        return Response(StockMovementSerializer(queryset, many=True).data)
