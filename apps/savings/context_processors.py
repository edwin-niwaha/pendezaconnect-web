from .models import SavingsTransaction


def savings_notifications_context(request):
    user = getattr(request, "user", None)
    profile = getattr(user, "profile", None)
    role = getattr(profile, "resolved_staff_role", "") or getattr(profile, "role", "")

    if not getattr(user, "is_authenticated", False) or role not in {
        "administrator",
        "hof",
        "accountant",
    }:
        return {
            "pending_withdrawal_requests": SavingsTransaction.objects.none(),
            "pending_withdrawal_count": 0,
        }

    pending_withdrawals = SavingsTransaction.objects.select_related("account", "account__client").filter(
        status="pending",
        transaction_type="withdrawal",
    )
    return {
        "pending_withdrawal_requests": pending_withdrawals[:5],
        "pending_withdrawal_count": pending_withdrawals.count(),
    }
