from rest_framework import serializers

from apps.users.models import UserNotification


class UserNotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()
    data = serializers.SerializerMethodField()

    class Meta:
        model = UserNotification
        fields = ("id", "event", "record_id", "title", "body", "is_read", "data", "created_at")
        read_only_fields = fields

    def get_is_read(self, obj):
        return obj.read_at is not None

    def get_data(self, obj):
        data = {"event": obj.event}
        if obj.record_id is not None:
            data["record_id"] = obj.record_id
        return data
