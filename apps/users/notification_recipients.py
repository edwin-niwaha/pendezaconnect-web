from django.db.models import Q

from apps.users.models import Profile


class NotificationRecipients:
    STAFF_ROLES = frozenset({"administrator", "manager", "staff", "boo", "hof", "accountant", "ed"})

    @staticmethod
    def staff():
        return (
            Profile.objects.filter(user__is_active=True)
            .filter(
                Q(account_type="staff", staff_role__in=NotificationRecipients.STAFF_ROLES)
                | Q(role__in=NotificationRecipients.STAFF_ROLES)
            )
            .values_list("user_id", flat=True)
        )

    @staticmethod
    def staff_roles(*roles):
        """Return active staff assigned to one of the exact workflow roles."""
        selected = {str(role).strip().lower() for role in roles if role}
        if not selected:
            return Profile.objects.none().values_list("user_id", flat=True)
        return (
            Profile.objects.filter(user__is_active=True)
            .filter(Q(staff_role__in=selected) | Q(role__in=selected))
            .values_list("user_id", flat=True)
            .distinct()
        )

    @staticmethod
    def clients(client_id):
        return Profile.objects.filter(
            client_id=client_id,
            user__is_active=True,
        ).values_list("user_id", flat=True)

    @staticmethod
    def sponsors(sponsor_id):
        return Profile.objects.filter(
            sponsor_id=sponsor_id,
            user__is_active=True,
        ).values_list("user_id", flat=True)
