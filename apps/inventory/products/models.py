from cloudinary.models import CloudinaryField
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.forms import model_to_dict

from apps.inventory.supplier.models import Supplier

# Define choices for product status
STATUS_CHOICES = [
    ("", "-- Choose status --"),
    ("ACTIVE", "Active"),
    ("INACTIVE", "Inactive"),
]


class Category(models.Model):
    name = models.CharField(
        max_length=100,
        verbose_name="Name",
    )
    description = models.CharField(max_length=50, blank=True, verbose_name="Description")

    class Meta:
        db_table = "category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=256, verbose_name="Product Name")
    description = models.TextField(verbose_name="Product Description")
    status = models.CharField(choices=STATUS_CHOICES, max_length=10, verbose_name="Status")
    category = models.ForeignKey(
        Category,
        related_name="products",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Category",
    )
    supplier = models.ForeignKey(
        Supplier,
        related_name="products",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Supplier",
    )
    cost = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Cost Price")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Selling Price")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        db_table = "product"

    def __str__(self):
        return self.name

    def to_json(self):
        item = model_to_dict(self)
        item.update(
            {
                "id": self.id,
                "text": self.name,
                "category": self.category.name if self.category else None,
                "quantity": self.stock_on_hand,
                "total_product": 0,
            }
        )
        return item

    def profit_margin(self):
        """Calculate and return the profit margin as a percentage."""
        if self.price and self.cost:
            return round(((self.price - self.cost) / self.price) * 100, 2)
        return 0  # return 0 if there's no valid price or cost

    @property
    def prefixed_id(self):
        return f"SKU{self.pk:03d}"

    @property
    def active_variants(self):
        return self.variants.filter(status="ACTIVE")

    @property
    def has_variants(self):
        return self.variants.exists()

    @property
    def base_stock(self):
        return self.inventory.quantity if hasattr(self, "inventory") else 0

    @property
    def variant_stock(self):
        return self.variants.aggregate(total=models.Sum("quantity"))["total"] or 0

    @property
    def stock_on_hand(self):
        if self.has_variants:
            return self.variant_stock
        return self.base_stock

    @property
    def stock_status(self):
        if self.stock_on_hand <= 0:
            return "Out of stock"
        if hasattr(self, "inventory") and self.stock_on_hand <= self.inventory.low_stock_threshold:
            return "Low stock"
        return "In stock"


class ProductVariant(models.Model):
    product = models.ForeignKey(
        Product,
        related_name="variants",
        on_delete=models.CASCADE,
        verbose_name="Product",
    )
    name = models.CharField(max_length=120, verbose_name="Variant Name")
    sku = models.CharField(max_length=64, unique=True, verbose_name="SKU")
    barcode = models.CharField(max_length=64, blank=True, verbose_name="Barcode")
    option_value = models.CharField(
        max_length=120,
        blank=True,
        verbose_name="Option Value",
        help_text="Example: Small, Blue, 500ml, Pack of 12.",
    )
    cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Cost Price",
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Selling Price",
    )
    quantity = models.PositiveIntegerField(default=0, verbose_name="Stock Quantity")
    low_stock_threshold = models.PositiveIntegerField(default=5, verbose_name="Low Stock Threshold")
    status = models.CharField(
        choices=STATUS_CHOICES,
        max_length=10,
        default="ACTIVE",
        verbose_name="Status",
    )
    is_default = models.BooleanField(default=False, verbose_name="Default Variant")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated At")

    class Meta:
        db_table = "product_variant"
        ordering = ["product__name", "name"]
        unique_together = (("product", "name"),)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

    @property
    def display_name(self):
        return f"{self.product.name} - {self.name}"

    @property
    def effective_cost(self):
        return self.cost if self.cost is not None else self.product.cost

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def is_low_stock(self):
        return 0 < self.quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.quantity <= 0

    @property
    def stock_status(self):
        if self.is_out_of_stock:
            return "Out of stock"
        if self.is_low_stock:
            return "Low stock"
        return "In stock"

    def adjust_stock(self, quantity_delta):
        new_quantity = self.quantity + quantity_delta
        if new_quantity < 0:
            raise ValidationError("Variant stock cannot be negative.")
        self.quantity = new_quantity
        self.save(update_fields=["quantity", "updated_at"])

    def to_json(self):
        return {
            "id": self.id,
            "text": self.display_name,
            "product": self.product.name,
            "sku": self.sku,
            "price": float(self.effective_price),
            "cost": float(self.effective_cost),
            "quantity": self.quantity,
        }


class ProductImage(models.Model):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    # image = models.ImageField(upload_to="product_images/", verbose_name="Product Image")
    image = CloudinaryField("image", blank=True, null=True)
    is_default = models.BooleanField(default=False, verbose_name="Is Default")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")

    class Meta:
        db_table = "product_image"
        verbose_name = "Product Image"
        verbose_name_plural = "Product Images"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Image for {self.product.name} (Default: {self.is_default})"

    def clean(self):
        # Ensure only one default image is set per product
        if self.is_default:
            default_image_exists = (
                ProductImage.objects.filter(product=self.product, is_default=True).exclude(id=self.id).exists()
            )

            if default_image_exists:
                raise ValidationError("Only one default image can be set per product.")

    def save(self, *args, **kwargs):
        # Ensure no other images are marked as default if this one is set as default
        if self.is_default:
            ProductImage.objects.filter(product=self.product, is_default=True).update(is_default=False)

        super().save(*args, **kwargs)


class Inventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="inventory")
    quantity = models.PositiveIntegerField(verbose_name="Stock Quantity", default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5, verbose_name="Low Stock Threshold")
    is_out_of_stock = models.BooleanField(default=False, verbose_name="Out of Stock")

    def check_stock_alerts(self):
        """Check stock levels and update stock status."""
        self.is_out_of_stock = self.quantity <= 0

    def save(self, *args, **kwargs):
        # Ensure stock alerts are checked before saving
        self.check_stock_alerts()
        super().save(*args, **kwargs)

    @property
    def is_low_stock(self):
        return 0 < self.quantity <= self.low_stock_threshold

    @property
    def stock_status(self):
        if self.is_out_of_stock:
            return "Out of stock"
        if self.is_low_stock:
            return "Low stock"
        return "In stock"

    def adjust_stock(self, quantity_delta):
        new_quantity = self.quantity + quantity_delta
        if new_quantity < 0:
            raise ValidationError("Product stock cannot be negative.")
        self.quantity = new_quantity
        self.save(update_fields=["quantity", "is_out_of_stock"])

    def __str__(self):
        return f"{self.product.name} - Stock: {self.quantity}"


class StockMovement(models.Model):
    STOCK_IN = "IN"
    STOCK_OUT = "OUT"
    ADJUSTMENT = "ADJUSTMENT"
    SALE = "SALE"
    RETURN = "RETURN"

    MOVEMENT_TYPE_CHOICES = [
        (STOCK_IN, "Stock In"),
        (STOCK_OUT, "Stock Out"),
        (ADJUSTMENT, "Adjustment"),
        (SALE, "Sale"),
        (RETURN, "Return"),
    ]

    product = models.ForeignKey(
        Product,
        related_name="stock_movements",
        on_delete=models.CASCADE,
        verbose_name="Product",
    )
    variant = models.ForeignKey(
        ProductVariant,
        related_name="stock_movements",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Variant",
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    quantity = models.IntegerField(verbose_name="Quantity Change")
    unit_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Unit Cost",
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Unit Price",
    )
    reference = models.CharField(max_length=100, blank=True, verbose_name="Reference")
    notes = models.TextField(blank=True, verbose_name="Notes")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="inventory_stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        db_table = "stock_movement"
        ordering = ["-created_at"]

    def __str__(self):
        item = self.variant.display_name if self.variant else self.product.name
        return f"{item}: {self.movement_type} {self.quantity}"
