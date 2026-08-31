from rest_framework import serializers

from apps.finance.models import ChildPayments, Payment, StaffPayments


class PaymentSerializer(serializers.ModelSerializer):
    sponsor_name = serializers.SerializerMethodField()
    sponsor_code = serializers.CharField(source="sponsor.prefixed_id", read_only=True)
    program_name = serializers.CharField(source="program.name", read_only=True)
    child_name = serializers.CharField(source="child.full_name", read_only=True)
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = (
            "id",
            "sponsor",
            "sponsor_name",
            "sponsor_code",
            "program_name",
            "child_name",
            "staff_name",
            "amount",
            "payment_date",
            "reference",
            "notes",
        )

    def get_sponsor_name(self, obj):
        return str(obj.sponsor).strip()

    def get_staff_name(self, obj):
        return str(obj.staff).strip() if obj.staff_id else None


class ChildPaymentSerializer(serializers.ModelSerializer):
    sponsor_name = serializers.SerializerMethodField()
    child_name = serializers.CharField(source="child.full_name", read_only=True)

    class Meta:
        model = ChildPayments
        fields = (
            "id",
            "sponsor",
            "sponsor_name",
            "child_name",
            "amount",
            "payment_date",
            "month",
            "payment_year",
            "is_valid",
        )

    def get_sponsor_name(self, obj):
        return str(obj.sponsor).strip()


class StaffPaymentSerializer(serializers.ModelSerializer):
    sponsor_name = serializers.SerializerMethodField()
    staff_name = serializers.SerializerMethodField()

    class Meta:
        model = StaffPayments
        fields = (
            "id",
            "sponsor",
            "sponsor_name",
            "staff_name",
            "amount",
            "payment_date",
            "month",
            "payment_year",
            "is_valid",
        )

    def get_sponsor_name(self, obj):
        return str(obj.sponsor).strip()

    def get_staff_name(self, obj):
        return str(obj.staff).strip()
