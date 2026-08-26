import logging

from django.conf import settings
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth.models import User
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from api.v1.serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    GoogleLoginSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)
from apps.users.tasks import queue_user_notification
from api.v1.throttles import LoginThrottle, PasswordResetThrottle

logger = logging.getLogger(__name__)


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [permissions.AllowAny]

    @action(detail=False, methods=["post"], url_path="login", throttle_classes=[LoginThrottle])
    def login(self, request):
        username = request.data.get("username") or request.data.get("email")
        password = request.data.get("password")
        user = authenticate(request, username=username, password=password)
        if not user:
            return Response(
                {"detail": "Invalid username or password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not user.is_active:
            return Response(
                {"detail": "This account is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserProfileSerializer(user, context={"request": request}).data,
            }
        )

    @action(detail=False, methods=["post"], url_path="google")
    def google(self, request):
        serializer = GoogleLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserProfileSerializer(user, context={"request": request}).data,
            }
        )

    @action(
        detail=False,
        methods=["get"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="me",
    )
    def me(self, request):
        return Response(UserProfileSerializer(request.user, context={"request": request}).data)

    @action(
        detail=False,
        methods=["patch"],
        permission_classes=[permissions.IsAuthenticated],
        url_path="profile",
    )
    def profile(self, request):
        serializer = UserProfileUpdateSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserProfileSerializer(user, context={"request": request}).data)

    @action(
        detail=False,
        methods=["post", "patch"],
        parser_classes=[MultiPartParser, FormParser],
        permission_classes=[permissions.IsAuthenticated],
        url_path="avatar",
    )
    def avatar(self, request):
        serializer = AvatarUploadSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserProfileSerializer(user, context={"request": request}).data)

    @action(
        detail=False,
        methods=["post"],
        authentication_classes=[],
        permission_classes=[permissions.AllowAny],
        url_path="logout",
    )
    def logout(self, request):
        refresh_value = str(request.data.get("refresh", "")).strip()
        if not refresh_value:
            return Response({"refresh": ["Refresh token is required."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh_value).blacklist()
        except TokenError:
            return Response({"refresh": ["Refresh token is invalid or expired."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=["post"],
        parser_classes=[JSONParser],
        permission_classes=[permissions.IsAuthenticated],
        url_path="password/change",
    )
    def change_password(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        update_session_auth_hash(request, user)
        queue_user_notification([user.id], "account_security_changed")
        return Response({"detail": "Password changed successfully."})

    @action(detail=False, methods=["post"], url_path="password/reset", throttle_classes=[PasswordResetThrottle])
    def reset_password(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        if not email:
            return Response(
                {"detail": "Enter the email address connected to your account."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if request.user.is_authenticated and not User.objects.filter(
            email__iexact=email, is_active=True
        ).exists():
            return Response(
                {"detail": "No active account was found with that email address."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not settings.DEFAULT_FROM_EMAIL:
            return Response(
                {"detail": "Password reset email is not configured on the server."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        form = PasswordResetForm(data={"email": email})
        form.is_valid()
        if form.cleaned_data.get("email"):
            try:
                form.save(
                    request=request,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    email_template_name="accounts/password_reset_email.html",
                    subject_template_name="accounts/password_reset_subject",
                )
            except Exception as exc:
                logger.exception("Password reset email failed for %s", email)
                return Response(
                    {"detail": f"Could not send the reset email: {exc}"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response(
            {
                "detail": (
                    "If an account exists with that email address, password reset "
                    "instructions have been sent."
                )
            }
        )
