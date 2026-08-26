from django.urls import reverse

STAFF_ROLE_LABELS = {
    "administrator": "Administrator",
    "manager": "Manager",
    "staff": "Staff",
    "boo": "Business Operations Officer",
    "hof": "Head of Finance",
    "accountant": "Accountant",
    "ed": "Executive Director",
}


def get_profile(user):
    if not getattr(user, "is_authenticated", False):
        return None
    return getattr(user, "profile", None)


def get_account_type(user):
    profile = get_profile(user)
    if not profile:
        return "guest"
    return profile.resolved_account_type


def get_staff_role(user):
    profile = get_profile(user)
    if not profile:
        return ""
    return profile.resolved_staff_role


def is_staff_user(user, roles=None):
    profile = get_profile(user)
    if not profile or profile.resolved_account_type != "staff":
        return False
    if roles is None:
        return True
    if isinstance(roles, str):
        roles = {roles}
    return profile.resolved_staff_role in set(roles)


def is_client_user(user):
    profile = get_profile(user)
    return bool(profile and profile.resolved_account_type == "client")


def is_sponsor_user(user):
    profile = get_profile(user)
    return bool(profile and profile.resolved_account_type == "sponsor")


def get_login_redirect_url(user, redirect_to=None):
    """Return an explicit destination or keep normal sign-ins on the landing page."""
    if redirect_to:
        return redirect_to
    return reverse("users-home")
