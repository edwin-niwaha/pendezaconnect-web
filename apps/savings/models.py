from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from apps.client.models import Client


class SavingsAccount(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("dormant", "Dormant"),
        ("closed", "Closed"),
    ]

    client = models.OneToOneField(
        Client,
        on_delete=models.CASCADE,
        related_name="savings_account",
    )
    account_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    opening_date = models.DateField(default=date.today)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="active")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_savings_accounts",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "savings_accounts"
        ordering = ["client__full_name"]
        indexes = [
            models.Index(fields=["status", "opening_date"], name="savings_status_open_idx"),
        ]

    def save(self, *args, **kwargs):
        needs_number = not self.account_number
        super().save(*args, **kwargs)
        if needs_number:
            self.account_number = f"SAV-{self.pk:06d}"
            SavingsAccount.objects.filter(pk=self.pk).update(account_number=self.account_number)

    @property
    def balance(self):
        totals = self.transactions.filter(status="approved").aggregate(
            credits=Sum("amount", filter=Q(transaction_type__in=SavingsTransaction.CREDIT_TYPES)),
            debits=Sum("amount", filter=Q(transaction_type__in=SavingsTransaction.DEBIT_TYPES)),
        )
        return (totals["credits"] or Decimal("0.00")) - (totals["debits"] or Decimal("0.00"))

    def __str__(self):
        return f"{self.account_number or 'New Savings Account'} - {self.client.full_name}"


class SavingsTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ("deposit", "Deposit"),
        ("withdrawal", "Withdrawal"),
        ("interest", "Interest"),
        ("charge", "Charge"),
        ("adjustment_credit", "Adjustment Credit"),
        ("adjustment_debit", "Adjustment Debit"),
    ]
    CREDIT_TYPES = {"deposit", "interest", "adjustment_credit"}
    DEBIT_TYPES = {"withdrawal", "charge", "adjustment_debit"}

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("cash", "Cash"),
        ("mobile_money", "Mobile Money"),
        ("bank_transfer", "Bank Transfer"),
        ("cheque", "Cheque"),
        ("system", "System"),
    ]

    account = models.ForeignKey(
        SavingsAccount,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_type = models.CharField(max_length=25, choices=TRANSACTION_TYPE_CHOICES)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    transaction_date = models.DateField(default=date.today)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="cash")
    reference = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default="approved")
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_savings_transactions",
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recorded_savings_transactions",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_savings_transactions",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "savings_transactions"
        ordering = ["-transaction_date", "-created_at"]
        indexes = [
            models.Index(
                fields=["account", "status", "transaction_date"],
                name="savings_txn_account_status_idx",
            ),
            models.Index(
                fields=["status", "transaction_date"],
                name="savings_txn_status_date_idx",
            ),
        ]

    @property
    def is_credit(self):
        return self.transaction_type in self.CREDIT_TYPES

    @property
    def is_debit(self):
        return self.transaction_type in self.DEBIT_TYPES

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than zero."})
        if self.account_id and self.account.status != "active" and self.status != "rejected":
            raise ValidationError("Savings transactions can only be recorded on active accounts.")
        if self.status == "approved" and self.is_debit and self.account_id:
            current_balance = self.account.balance
            if self.pk:
                previous = SavingsTransaction.objects.filter(pk=self.pk, status="approved").first()
                if previous and previous.is_debit:
                    current_balance += previous.amount
                elif previous and previous.is_credit:
                    current_balance -= previous.amount
            if self.amount > current_balance:
                raise ValidationError({"amount": "Withdrawal or charge cannot exceed the available savings balance."})

    def approve(self, user):
        self.status = "approved"
        self.approved_by = user
        self.approved_at = timezone.now()
        self.full_clean()
        self.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return self

    def reject(self, user):
        self.status = "rejected"
        self.approved_by = user
        self.approved_at = timezone.now()
        self.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
        return self

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_transaction_type_display()} {self.amount} - {self.account}"
