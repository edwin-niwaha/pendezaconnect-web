from rest_framework import serializers

from apps.sponsor.models import Sponsor


class SponsorSerializer(serializers.ModelSerializer):
    prefixed_id = serializers.CharField(read_only=True)
    full_name = serializers.SerializerMethodField()
    mobile_telephone = serializers.CharField(read_only=True)

    class Meta:
        model = Sponsor
        fields = (
            "id",
            "prefixed_id",
            "full_name",
            "first_name",
            "last_name",
            "email",
            "mobile_telephone",
            "sponsorship_type",
            "is_child_sponsor",
            "is_staff_sponsor",
            "is_family_supporter",
            "is_general_donor",
            "is_one_time_donor",
            "is_departed",
        )

    def get_full_name(self, obj):
        return str(obj).strip()
