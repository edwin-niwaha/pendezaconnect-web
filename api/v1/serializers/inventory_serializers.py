from rest_framework import serializers

from apps.inventory.products.models import Product, StockMovement


class InventoryProductSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="prefixed_id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    supplier_name = serializers.CharField(source="supplier.name", read_only=True, allow_null=True)
    stock_on_hand = serializers.IntegerField(read_only=True)
    stock_status = serializers.SerializerMethodField()
    margin = serializers.DecimalField(source="profit_margin", max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "sku",
            "name",
            "description",
            "status",
            "category_name",
            "supplier_name",
            "cost",
            "price",
            "stock_on_hand",
            "stock_status",
            "margin",
            "updated_at",
        ]

    def get_stock_status(self, obj):
        if obj.stock_on_hand <= 0:
            return "Out of stock"
        if obj.has_variants:
            return "Low stock" if any(variant.is_low_stock for variant in obj.active_variants) else "In stock"
        return obj.inventory.stock_status if hasattr(obj, "inventory") else "Out of stock"


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    variant_name = serializers.CharField(source="variant.name", read_only=True, allow_null=True)
    movement_label = serializers.CharField(source="get_movement_type_display", read_only=True)
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "product",
            "product_name",
            "variant",
            "variant_name",
            "movement_type",
            "movement_label",
            "quantity",
            "reference",
            "notes",
            "created_by_name",
            "created_at",
        ]

    def get_created_by_name(self, obj):
        if not obj.created_by:
            return None
        return obj.created_by.get_full_name() or obj.created_by.get_username()
