from rest_framework import serializers

from apps.child.models import Child, ChildProfilePicture
from .media import absolute_media_url


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
        prefetched = getattr(obj, "current_profile_pictures", None)
        if prefetched is None:
            picture = obj.get_current_profile_picture()
        else:
            picture = prefetched[0] if prefetched else None
        if not picture or not picture.picture:
            return None
        return absolute_media_url(self, picture.picture)


class ChildPhotoUploadSerializer(serializers.ModelSerializer):
    picture_url = serializers.SerializerMethodField()

    class Meta:
        model = ChildProfilePicture
        fields = ("id", "child", "picture", "picture_url", "uploaded_at", "is_current")
        read_only_fields = ("id", "child", "picture_url", "uploaded_at", "is_current")

    def get_picture_url(self, obj):
        return absolute_media_url(self, obj.picture)
