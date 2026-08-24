from django.db.models import Count, Q

from decimal import Decimal

from django.db.models import DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.child.models import Child
from apps.client.models import Client
from apps.finance.models import ChildPayments, Payment, StaffPayments
from apps.loans.models import Loan
from apps.savings.models import SavingsAccount, SavingsTransaction
from apps.sponsor.models import Sponsor
from apps.staff.models import Staff

INTERNAL_ROLES = {"administrator", "manager", "staff", "boo", "hof", "ed", "accountant"}


def user_profile(user):
    return getattr(user, "profile", None)


def resolved_account_type(user):
    profile = user_profile(user)
    return getattr(profile, "resolved_account_type", "guest")


def resolved_staff_role(user):
    profile = user_profile(user)
    return getattr(profile, "resolved_staff_role", "")


def is_internal_user(user):
    if not getattr(user, "is_authenticated", False):
        return False
    profile = user_profile(user)
    role = getattr(profile, "role", "")
    return (
        resolved_account_type(user) == "staff"
        or role in INTERNAL_ROLES
        or resolved_staff_role(user) in INTERNAL_ROLES
        or getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
    )


def linked_client_id(user):
    profile = user_profile(user)
    return getattr(profile, "client_id", None)


def linked_sponsor_id(user):
    profile = user_profile(user)
    return getattr(profile, "sponsor_id", None)


def sponsors_for_user(user):
    queryset = Sponsor.objects.active().order_by("id")
    if is_internal_user(user):
        return queryset
    sponsor_id = linked_sponsor_id(user)
    if not sponsor_id:
        return queryset.none()
    return queryset.filter(id=sponsor_id)


def clients_for_user(user):
    money_field = DecimalField(max_digits=15, decimal_places=2)
    savings_balance = (
        SavingsAccount.objects.filter(client_id=OuterRef("pk"))
        .annotate(
            credits=Coalesce(
                Sum("transactions__amount", filter=Q(transactions__status="approved", transactions__transaction_type__in=SavingsTransaction.CREDIT_TYPES)),
                Value(Decimal("0.00")),
                output_field=money_field,
            ),
            debits=Coalesce(
                Sum("transactions__amount", filter=Q(transactions__status="approved", transactions__transaction_type__in=SavingsTransaction.DEBIT_TYPES)),
                Value(Decimal("0.00")),
                output_field=money_field,
            ),
        )
        .annotate(calculated_balance=ExpressionWrapper(F("credits") - F("debits"), output_field=money_field))
        .values("calculated_balance")[:1]
    )
    queryset = (
        Client.objects.select_related("savings_account")
        .annotate(
            active_loans_count=Count(
                "loans",
                filter=Q(loans__status__in=Loan.ACTIVE_STATUSES),
            ),
            calculated_savings_balance=Coalesce(
                Subquery(savings_balance, output_field=money_field),
                Value(Decimal("0.00")),
                output_field=money_field,
            ),
        )
        .order_by("id")
    )
    if is_internal_user(user):
        return queryset
    client_id = linked_client_id(user)
    if not client_id:
        return queryset.none()
    return queryset.filter(id=client_id)


def children_for_user(user, scope=""):
    queryset = Child.objects.all()
    if is_internal_user(user):
        if scope == "departed":
            queryset = queryset.filter(is_departed=True)
        else:
            queryset = queryset.filter(is_departed=False)
            if scope == "sponsored":
                queryset = queryset.filter(is_sponsored=True)
            elif scope == "non-sponsored":
                queryset = queryset.filter(is_sponsored=False)
        return queryset.order_by("id")
    return queryset.none()


def staff_for_user(user, scope=""):
    if not is_internal_user(user):
        return Staff.objects.none()
    queryset = Staff.objects.prefetch_related("departures")
    if scope == "departed":
        queryset = queryset.filter(is_departed=True)
    else:
        queryset = queryset.filter(is_departed=False)
        if scope == "sponsored":
            queryset = queryset.filter(is_sponsored=True)
        elif scope == "non-sponsored":
            queryset = queryset.filter(is_sponsored=False)
    return queryset.order_by("id")


def loans_for_user(user):
    queryset = Loan.objects.select_related("borrower").order_by("-id")
    if is_internal_user(user):
        return queryset
    client_id = linked_client_id(user)
    if not client_id:
        return queryset.none()
    return queryset.filter(borrower_id=client_id)


def payments_for_user(user):
    queryset = Payment.objects.with_related().order_by("-payment_date", "-id")
    if is_internal_user(user):
        return queryset
    sponsor_id = linked_sponsor_id(user)
    if not sponsor_id:
        return queryset.none()
    return queryset.filter(sponsor_id=sponsor_id)


def child_payments_for_sponsor(sponsor):
    return ChildPayments.objects.select_related("sponsor", "child").filter(sponsor=sponsor)


def staff_payments_for_sponsor(sponsor):
    return StaffPayments.objects.select_related("sponsor", "staff").filter(sponsor=sponsor)


def savings_accounts_for_client(client):
    return SavingsAccount.objects.filter(client=client)


def savings_transactions_for_client(client):
    return SavingsTransaction.objects.select_related(
        "account",
        "account__client",
    ).filter(account__client=client)


def dashboard_for_user(user):
    client_id = linked_client_id(user)
    sponsor_id = linked_sponsor_id(user)

    if is_internal_user(user):
        return {
            "account_type": "staff",
            "sponsors": Sponsor.objects.active().count(),
            "clients": Client.objects.count(),
            "staff": Staff.objects.filter(is_departed=False).count(),
            "children": {
                "total": Child.objects.count(),
                "sponsored": Child.objects.filter(is_sponsored=True).count(),
                "non_sponsored": Child.objects.filter(is_sponsored=False).count(),
                "departed": Child.objects.filter(is_departed=True).count(),
            },
            "staff_workforce": {
                "total": Staff.objects.count(),
                "sponsored": Staff.objects.filter(is_sponsored=True).count(),
                "non_sponsored": Staff.objects.filter(is_sponsored=False).count(),
                "departed": Staff.objects.filter(is_departed=True).count(),
            },
            "loans": {
                "pending": Loan.objects.filter(status="pending").count(),
                "approved": Loan.objects.filter(status="approved").count(),
                "active": Loan.objects.filter(status__in=Loan.ACTIVE_STATUSES).count(),
                "overdue": Loan.objects.filter(status="overdue").count(),
            },
            "payments": {
                "sponsor_payments": Payment.objects.count(),
                "child_payments": ChildPayments.objects.count(),
                "staff_payments": StaffPayments.objects.count(),
            },
        }

    if client_id:
        loans = Loan.objects.filter(borrower_id=client_id)
        savings = SavingsAccount.objects.filter(client_id=client_id).first()
        return {
            "account_type": "client",
            "loans": {
                "total": loans.count(),
                "active": loans.filter(status__in=Loan.ACTIVE_STATUSES).count(),
                "overdue": loans.filter(status="overdue").count(),
            },
            "savings_balance": savings.balance if savings else 0,
        }

    if sponsor_id:
        return {
            "account_type": "sponsor",
            "payments": {
                "sponsor_payments": Payment.objects.filter(sponsor_id=sponsor_id).count(),
                "child_payments": ChildPayments.objects.filter(sponsor_id=sponsor_id).count(),
                "staff_payments": StaffPayments.objects.filter(sponsor_id=sponsor_id).count(),
            },
        }

    return {"account_type": "guest"}
