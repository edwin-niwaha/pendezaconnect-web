from rest_framework import serializers

from apps.users.models import Contact


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = Contact
        fields = ("id", "name", "email", "message", "created_at")
        read_only_fields = ("id", "created_at")

    def validate_message(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Tell us a little more (at least 10 characters).")
        return value
