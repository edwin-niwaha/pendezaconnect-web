from rest_framework import serializers

from apps.child.models import Child, ChildProfilePicture


class ChildSerializer(serializers.ModelSerializer):
    prefixed_id = serializers.CharField(read_only=True)
    current_picture_url = serializers.SerializerMethodField()

    class Meta:
        model = Child
        fields = (
            "id",
            "prefixed_id",
            "full_name",
            "preferred_name",
            "gender",
            "date_of_birth",
            "registration_date",
            "residence",
            "district",
            "tribe",
            "aspiration",
            "c_interest",
            "is_child_in_school",
            "guardian",
            "guardian_contact",
            "relationship_with_guardian",
            "health_status",
            "is_sponsored",
            "is_departed",
            "current_picture_url",
        )

    def get_current_picture_url(self, obj):
        picture = obj.get_current_profile_picture()
        if not picture or not picture.picture:
            return None
        return str(picture.picture)


class ChildPhotoUploadSerializer(serializers.ModelSerializer):
    picture_url = serializers.SerializerMethodField()

    class Meta:
        model = ChildProfilePicture
        fields = ("id", "child", "picture", "picture_url", "uploaded_at", "is_current")
        read_only_fields = ("id", "child", "picture_url", "uploaded_at", "is_current")

    def get_picture_url(self, obj):
        return str(obj.picture) if obj.picture else None
