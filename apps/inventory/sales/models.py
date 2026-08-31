from decimal import Decimal

import django.utils.timezone
from django.db import models

from apps.inventory.customers.models import Customer
from apps.inventory.products.models import Product, ProductVariant

PAYMENT_METHOD_CHOICES = [
    ("CREDIT_CARD", "Credit Card"),
    ("DEBIT_CARD", "Debit Card"),
    ("PAYPAL", "PayPal"),
    ("BANK_TRANSFER", "Bank Transfer"),
    ("CASH", "Cash"),
    ("MTN_MOBILE_MONEY", "MTN Mobile Money"),
    ("AIRTEL_MONEY", "Airtel Money"),
]

SALE_TYPE_CHOICES = [
    ("online", "Online"),
    ("offline", "Offline"),
]


# =================================== Sale model ===================================
class Sale(models.Model):
    sale_type = models.CharField(max_length=10, choices=SALE_TYPE_CHOICES, default="offline")
    date_added = models.DateTimeField(default=django.utils.timezone.now)
    trans_date = models.DateField(verbose_name="Receipt Date")
    receipt_number = models.CharField(max_length=50, unique=True, blank=True, null=True)
    customer = models.ForeignKey(Customer, related_name="sales", on_delete=models.SET_NULL, null=True, blank=True)
    sub_total = models.FloatField(default=0)
    grand_total = models.FloatField(default=0)
    tax_amount = models.FloatField(default=0)
    tax_percentage = models.FloatField(default=0)
    amount_payed = models.FloatField(default=0)
    amount_change = models.FloatField(default=0)
    payment_method = models.CharField(
        max_length=50,
        choices=PAYMENT_METHOD_CHOICES,
        default="CASH",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")

    class Meta:
        db_table = "Sales"

    def __str__(self) -> str:
        return (
            "Sale ID: "
            + str(self.id)
            + " | Grand Total: "
            + str(self.grand_total)
            + " | Datetime: "
            + str(self.date_added)
        )

    def sum_items(self):
        details = SaleDetail.objects.filter(sale=self.id)
        return sum([d.quantity for d in details])


# =================================== SaleDetail model ===================================
class SaleDetail(models.Model):
    sale = models.ForeignKey(Sale, related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sale_details",
    )
    price = models.FloatField()
    quantity = models.IntegerField()
    total_detail = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created at")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Updated at")

    class Meta:
        db_table = "SaleDetails"

    def calculate_profit(self):
        # Convert price to Decimal to ensure compatibility with cost, then calculate profit
        cost = self.variant.effective_cost if self.variant else self.product.cost
        return (Decimal(self.price) - cost) * self.quantity

    @property
    def item_name(self):
        return self.variant.display_name if self.variant else self.product.name

    def __str__(self) -> str:
        return "Detail ID: " + str(self.id) + " Sale ID: " + str(self.sale.id) + " Quantity: " + str(self.quantity)
