from rest_framework import serializers

from apps.staff.models import Staff
from .media import absolute_media_url, thumbnail_url


class StaffSerializer(serializers.ModelSerializer):
    prefixed_id = serializers.CharField(read_only=True)
    full_name = serializers.SerializerMethodField()
    mobile_telephone = serializers.CharField(read_only=True)
    current_picture_url = serializers.SerializerMethodField()
    picture_url = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    departure_date = serializers.SerializerMethodField()

    class Meta:
        model = Staff
        fields = (
            "id",
            "prefixed_id",
            "full_name",
            "first_name",
            "last_name",
            "email",
            "mobile_telephone",
            "gender",
            "date_of_birth",
            "date_started_work",
            "department",
            "job_title",
            "is_departed",
            "is_sponsored",
            "departure_date",
            "current_picture_url",
            "picture_url",
            "photo_url",
            "thumbnail_url",
        )

    def get_full_name(self, obj):
        return str(obj).strip()

    def get_current_picture_url(self, obj):
        return absolute_media_url(self, obj.picture)

    def get_picture_url(self, obj):
        return self.get_current_picture_url(obj)

    def get_photo_url(self, obj):
        return self.get_current_picture_url(obj)

    def get_thumbnail_url(self, obj):
        return thumbnail_url(self, obj.picture)

    def get_departure_date(self, obj):
        departures = list(obj.departures.all())
        departure = max(departures, key=lambda item: (item.departure_date is not None, item.departure_date, item.id), default=None)
        return departure.departure_date if departure else None
