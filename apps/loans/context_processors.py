from apps.loans.models import Loan


def loan_dashboard_context(request):
    user = getattr(request, "user", None)
    profile = getattr(user, "profile", None)
    role = getattr(profile, "resolved_staff_role", "") or getattr(profile, "role", "")
    can_review_loans = getattr(user, "is_authenticated", False) and role in {
        "administrator",
        "manager",
        "staff",
        "boo",
        "hof",
        "accountant",
        "ed",
    }
    pending_applications = (
        Loan.objects.select_related("borrower").filter(status="pending").order_by("-created_at")
        if can_review_loans
        else Loan.objects.none()
    )
    return {
        "due_loans_count": 0,
        "overdue_loans_count": 0,
        "pending_loan_applications": pending_applications[:5],
        "pending_loan_application_count": pending_applications.count(),
    }
