from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from apps.client.models import Client
from apps.savings.models import SavingsAccount, SavingsTransaction

from .media import absolute_media_url, thumbnail_url


class ClientSerializer(serializers.ModelSerializer):
    prefixed_id = serializers.CharField(read_only=True)
    mobile_telephone = serializers.CharField(read_only=True)
    active_loans_count = serializers.IntegerField(read_only=True, default=0)
    savings_balance = serializers.SerializerMethodField()
    current_picture_url = serializers.SerializerMethodField()
    picture_url = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = (
            "id",
            "prefixed_id",
            "reg_number",
            "full_name",
            "email",
            "mobile_telephone",
            "active_loans_count",
            "savings_balance",
            "current_picture_url",
            "picture_url",
            "photo_url",
            "thumbnail_url",
        )

    def get_savings_balance(self, obj):
        annotated_balance = getattr(obj, "calculated_savings_balance", None)
        if annotated_balance is not None:
            return annotated_balance
        account = getattr(obj, "savings_account", None)
        return account.balance if account else 0

    def get_current_picture_url(self, obj):
        return absolute_media_url(self, obj.picture)

    def get_picture_url(self, obj):
        return self.get_current_picture_url(obj)

    def get_photo_url(self, obj):
        return self.get_current_picture_url(obj)

    def get_thumbnail_url(self, obj):
        return thumbnail_url(self, obj.picture)


class SavingsAccountSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source="client.full_name", read_only=True)
    balance = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True)

    class Meta:
        model = SavingsAccount
        fields = (
            "id",
            "client",
            "client_name",
            "account_number",
            "opening_date",
            "status",
            "balance",
        )


class SavingsTransactionSerializer(serializers.ModelSerializer):
    account_number = serializers.CharField(source="account.account_number", read_only=True)
    client_name = serializers.CharField(source="account.client.full_name", read_only=True)

    class Meta:
        model = SavingsTransaction
        fields = (
            "id",
            "account",
            "account_number",
            "client_name",
            "transaction_type",
            "amount",
            "transaction_date",
            "payment_method",
            "status",
        )


class SavingsRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, min_value=Decimal("0.01"))
    notes = serializers.CharField(allow_blank=True, max_length=2000, required=False)
    payment_method = serializers.ChoiceField(choices=("mobile_money", "bank_transfer", "cash", "cheque"))
    reference = serializers.CharField(allow_blank=True, max_length=80, required=False)
    transaction_type = serializers.ChoiceField(choices=("deposit", "withdrawal"))

    def validate(self, attrs):
        account = self.context["account"]
        reference = attrs.get("reference", "").strip()
        transaction_type = attrs["transaction_type"]

        if transaction_type == "deposit" and not reference:
            raise serializers.ValidationError({"reference": "Enter the Mobile Money transaction ID."})
        if (
            transaction_type == "deposit"
            and account.transactions.filter(
                reference__iexact=reference,
                transaction_type="deposit",
            )
            .exclude(status="rejected")
            .exists()
        ):
            raise serializers.ValidationError({"reference": "A deposit with this transaction ID already exists."})
        if transaction_type == "withdrawal":
            pending = account.transactions.filter(transaction_type="withdrawal", status="pending").aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0")
            if attrs["amount"] > account.balance - pending:
                raise serializers.ValidationError(
                    {"amount": ("The withdrawal cannot exceed your available savings balance.")}
                )

        attrs["reference"] = reference
        attrs["notes"] = attrs.get("notes", "").strip()
        return attrs
