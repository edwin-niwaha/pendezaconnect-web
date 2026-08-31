"""Read-only operational queues; reviewing a notification never approves a record."""

from django.urls import reverse

from apps.savings.models import SavingsTransaction
from apps.sponsor.models import SponsorFeedback
from apps.users.models import Contact, Profile
from apps.users.roles import STAFF_ROLE_LABELS, is_staff_user


def has_web_role(user, roles):
    profile = getattr(user, "profile", None)
    return bool(
        getattr(user, "is_authenticated", False) and profile and (profile.role in roles or is_staff_user(user, roles))
    )


def queue_permissions(user):
    profile = getattr(user, "profile", None)
    resolved_role = getattr(profile, "resolved_staff_role", "") or getattr(profile, "role", "")
    return {
        "activations": has_web_role(user, {"administrator"}),
        "sponsor_feedback": has_web_role(user, set(STAFF_ROLE_LABELS)),
        "user_feedback": has_web_role(user, {"administrator", "manager", "ed", "hof"}),
        "withdrawals": bool(
            getattr(user, "is_authenticated", False) and resolved_role in {"administrator", "hof", "accountant"}
        ),
    }


def notification_work_queues(user):
    allowed = queue_permissions(user)
    queues = []
    if allowed["activations"]:
        guests = (
            Profile.objects.select_related("user")
            .filter(
                account_type="guest",
                role="guest",
                staff_role="",
                client__isnull=True,
                sponsor__isnull=True,
            )
            .order_by("-user__date_joined", "-pk")
        )
        queues.append(
            {
                "id": "activations",
                "title": "Activate User Accounts",
                "count": guests.count(),
                "items": [
                    {
                        "id": f"profile-{profile.pk}",
                        "title": profile.user.username,
                        "body": "Guest account awaiting account assignment",
                        "web_path": reverse("update_profile", args=[profile.pk]),
                    }
                    for profile in guests[:5]
                ],
                "links": [{"label": "Manage user accounts", "path": reverse("profile_list")}],
            }
        )

    feedback_items, feedback_links, feedback_count = [], [], 0
    if allowed["sponsor_feedback"]:
        feedback = SponsorFeedback.objects.unread().with_related().order_by("-created_at", "-pk")
        feedback_count += feedback.count()
        path = reverse("sponsor_feedback_report")
        feedback_links.append({"label": "Review sponsor feedback", "path": path})
        feedback_items.extend(
            {
                "id": f"sponsor-feedback-{item.pk}",
                "title": item.subject,
                "body": f"Sponsor: {item.sponsor.first_name} {item.sponsor.last_name}",
                "created_at": item.created_at.isoformat(),
                "web_path": path,
            }
            for item in feedback[:5]
        )
    if allowed["user_feedback"]:
        feedback = Contact.objects.filter(is_valid=False).order_by("-created_at", "-pk")
        feedback_count += feedback.count()
        path = reverse("user_feedback")
        feedback_links.append({"label": "Review user feedback", "path": path})
        feedback_items.extend(
            {
                "id": f"user-feedback-{item.pk}",
                "title": item.name,
                "body": item.message[:200],
                "created_at": item.created_at.isoformat(),
                "web_path": path,
            }
            for item in feedback[:5]
        )
    if feedback_links:
        queues.append(
            {
                "id": "feedback",
                "title": "User Feedback",
                "count": feedback_count,
                "items": sorted(feedback_items, key=lambda item: item["created_at"], reverse=True)[:5],
                "links": feedback_links,
            }
        )

    if allowed["withdrawals"]:
        withdrawals = (
            SavingsTransaction.objects.select_related("account__client")
            .filter(status="pending", transaction_type="withdrawal")
            .order_by("-pk")
        )
        queues.append(
            {
                "id": "withdrawals",
                "title": "Pending Withdrawals",
                "count": withdrawals.count(),
                "items": [
                    {
                        "id": f"withdrawal-{item.pk}",
                        "title": item.account.client.full_name,
                        "body": "Withdrawal awaiting review",
                        "amount": str(item.amount),
                        "client_id": item.account.client_id,
                        "web_path": reverse("savings_account_detail", args=[item.account_id]),
                    }
                    for item in withdrawals[:5]
                ],
                "links": [{"label": "Review withdrawals", "path": reverse("savings_account_list")}],
            }
        )
    return queues
