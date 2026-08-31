from django.contrib import messages
from django.shortcuts import redirect
from social_core.pipeline.social_auth import associate_by_email

from .models import Profile


def associate_verified_google_email(backend, details, response, user=None, *args, **kwargs):
    if getattr(backend, "name", "") != "google-oauth2" or user is not None:
        return None
    if not response.get("email_verified"):
        return None
    return associate_by_email(backend, details, user=user, *args, **kwargs)


def require_google_login_token(strategy, backend, user=None, *args, **kwargs):
    if getattr(backend, "name", "") != "google-oauth2" or user is None:
        return None

    request = getattr(strategy, "request", None)
    if request is None:
        return None

    Profile.objects.get_or_create(user=user)
    if not user.email:
        messages.error(
            request,
            "Your Google account did not provide an email address. Please sign in with your password.",
        )
        return redirect("login")

    return None
