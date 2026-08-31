import requests
from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from rest_framework import serializers
from social_django.models import UserSocialAuth

from api.v1.serializers.auth_serializers import UserProfileSerializer
from apps.users.models import Profile

GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField(required=False, write_only=True, trim_whitespace=True)
    access_token = serializers.CharField(required=False, write_only=True, trim_whitespace=True)

    def validate(self, attrs):
        access_token = attrs.get("access_token", "").strip()
        token = attrs.get("id_token", "").strip()

        if access_token:
            payload = self._validate_access_token(access_token)
        elif token:
            payload = self._validate_id_token(token)
        else:
            raise serializers.ValidationError({"detail": "Google access token or ID token is required."})

        email = (payload.get("email") or "").strip().lower()
        if not email or not payload.get("email_verified"):
            raise serializers.ValidationError({"detail": "Google account email must be verified."})

        try:
            user = self._resolve_or_create_user(email, payload)
        except IntegrityError as exc:
            user = User.objects.filter(email__iexact=email, is_active=True).first()
            if user is None:
                raise serializers.ValidationError(
                    {"detail": ("An account with this email already exists. Please try again.")}
                ) from exc
            Profile.objects.get_or_create(
                user=user,
                defaults={"account_type": "guest", "role": "guest"},
            )

        attrs["user"] = user
        return attrs

    @transaction.atomic
    def _resolve_or_create_user(self, email, payload):
        google_uid = str(payload.get("sub") or "").strip()
        if google_uid:
            social = (
                UserSocialAuth.objects.select_related("user").filter(provider="google-oauth2", uid=google_uid).first()
            )
            if social:
                if not social.user.is_active:
                    raise serializers.ValidationError(
                        {"detail": "The account linked to this Google login is inactive."}
                    )
                Profile.objects.get_or_create(
                    user=social.user,
                    defaults={"account_type": "guest", "role": "guest"},
                )
                return social.user

        users = list(User.objects.select_for_update().filter(email__iexact=email).order_by("id")[:2])
        if len(users) > 1:
            raise serializers.ValidationError(
                {
                    "detail": (
                        "More than one account uses this email. Contact support so the "
                        "duplicate accounts can be resolved safely."
                    )
                }
            )
        if users:
            user = users[0]
            if not user.is_active:
                raise serializers.ValidationError({"detail": "The account linked to this Google email is inactive."})
        else:
            user = User(
                username=self._available_username(email),
                email=email,
                first_name=(payload.get("given_name") or "").strip()[:150],
                last_name=(payload.get("family_name") or "").strip()[:150],
            )
            user.set_unusable_password()
            user.save()

        Profile.objects.get_or_create(
            user=user,
            defaults={"account_type": "guest", "role": "guest"},
        )
        if google_uid:
            social, created = UserSocialAuth.objects.get_or_create(
                provider="google-oauth2",
                uid=google_uid,
                defaults={"user": user},
            )
            if not created and social.user_id != user.id:
                raise serializers.ValidationError({"detail": "This Google account is linked to another user."})
        return user

    def _available_username(self, email):
        base = email.split("@", 1)[0][:140] or "google-user"
        candidate = base
        suffix = 1
        while User.objects.filter(username__iexact=candidate).exists():
            suffix += 1
            marker = f"-{suffix}"
            candidate = f"{base[:150 - len(marker)]}{marker}"
        return candidate

    def _validate_access_token(self, access_token):
        try:
            response = requests.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=getattr(settings, "SOCIAL_AUTH_REQUESTS_TIMEOUT", 10),
            )
        except requests.RequestException as exc:
            raise serializers.ValidationError({"detail": "Unable to reach Google authentication service."}) from exc

        if response.status_code != 200:
            raise serializers.ValidationError({"detail": "Invalid Google access token."})

        return response.json()

    def _validate_id_token(self, token):
        try:
            from google.auth.transport import requests as google_requests
            from google.oauth2 import id_token
        except ImportError as exc:
            raise serializers.ValidationError({"detail": "Google ID-token verification is not installed."}) from exc

        client_ids = getattr(settings, "MOBILE_GOOGLE_CLIENT_IDS", [])
        if not client_ids:
            raise serializers.ValidationError({"detail": "Google sign-in is not configured."})

        last_error = None
        for audience in client_ids:
            try:
                return id_token.verify_oauth2_token(token, google_requests.Request(), audience)
            except ValueError as exc:
                last_error = exc

        raise serializers.ValidationError({"detail": "Invalid Google sign-in token."}) from last_error


class GoogleLoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserProfileSerializer()
