from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.users.models import Profile
from .media import absolute_media_url


class UserProfileSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()
    account_type = serializers.SerializerMethodField()
    staff_role = serializers.SerializerMethodField()
    client_id = serializers.SerializerMethodField()
    sponsor_id = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "avatar_url",
            "bio",
            "role",
            "account_type",
            "staff_role",
            "client_id",
            "sponsor_id",
        )

    def _profile(self, obj):
        return getattr(obj, "profile", None)

    def get_role(self, obj):
        if getattr(obj, "is_superuser", False):
            return "administrator"
        if getattr(obj, "is_staff", False):
            return "staff"
        profile = self._profile(obj)
        return getattr(profile, "role", "guest")

    def get_account_type(self, obj):
        if getattr(obj, "is_superuser", False) or getattr(obj, "is_staff", False):
            return "staff"
        profile = self._profile(obj)
        return getattr(profile, "resolved_account_type", "guest")

    def get_staff_role(self, obj):
        if getattr(obj, "is_superuser", False):
            return "administrator"
        if getattr(obj, "is_staff", False):
            return "staff"
        profile = self._profile(obj)
        return getattr(profile, "resolved_staff_role", "")

    def get_client_id(self, obj):
        profile = self._profile(obj)
        return getattr(profile, "client_id", None)

    def get_sponsor_id(self, obj):
        profile = self._profile(obj)
        return getattr(profile, "sponsor_id", None)

    def get_avatar_url(self, obj):
        profile = self._profile(obj)
        avatar = getattr(profile, "avatar", None)
        if not avatar:
            return None
        return absolute_media_url(self, avatar)

    def get_bio(self, obj):
        profile = self._profile(obj)
        return getattr(profile, "bio", "")


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    bio = serializers.CharField(required=False, allow_blank=True, write_only=True)

    class Meta:
        model = User
        fields = ("username", "first_name", "last_name", "email", "bio")
        extra_kwargs = {
            "email": {"required": True, "allow_blank": False},
            "username": {"required": True, "allow_blank": False},
        }

    def validate_username(self, value):
        username = value.strip()
        if not username:
            raise serializers.ValidationError("Username is required.")
        if self.instance and self.instance.username.lower() == username.lower():
            return username
        qs = User.objects.filter(username__iexact=username)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This username is already in use.")
        return username

    def validate_email(self, value):
        email = value.strip().lower()
        if self.instance and self.instance.email.lower() == email:
            return email
        qs = User.objects.filter(email__iexact=email)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("This email is already in use.")
        return email

    def update(self, instance, validated_data):
        bio = validated_data.pop("bio", None)
        for field, value in validated_data.items():
            setattr(instance, field, value.strip() if isinstance(value, str) else value)
        instance.save()
        if bio is not None:
            profile, _ = Profile.objects.get_or_create(
                user=instance, defaults={"bio": "", "avatar": "default.jpg"}
            )
            profile.bio = bio.strip()
            profile.save(update_fields=["bio"])
        return instance


class AvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.ImageField()

    def save(self, **kwargs):
        user = self.context["request"].user
        profile, _ = Profile.objects.get_or_create(
            user=user, defaults={"bio": "", "avatar": "default.jpg"}
        )
        profile.avatar = self.validated_data["avatar"]
        profile.save(update_fields=["avatar"])
        return user


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "New password and confirmation do not match."}
            )
        validate_password(attrs["new_password"], self.context["request"].user)
        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password"])
        return user
