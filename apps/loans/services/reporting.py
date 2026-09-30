import csv
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import Iterable

from dateutil.relativedelta import relativedelta
from django.core.paginator import Paginator
from django.db.models import Q, QuerySet
from django.http import HttpResponse
from django.utils import timezone

from apps.loans.models import Loan, LoanRepayment
from core.report_cache import cached_report

STANDARD_AGING_BUCKETS = (
    "Current",
    "1-30 days overdue",
    "31-60 days overdue",
    "61-90 days overdue",
    "91-180 days overdue",
    "Over 180 days overdue",
)

PAR_THRESHOLDS = (
    ("PAR 1+", 1),
    ("PAR 30+", 30),
    ("PAR 60+", 60),
    ("PAR 90+", 90),
    ("PAR 120+", 120),
    ("PAR 180+", 180),
)


@dataclass(frozen=True)
class ReportColumn:
    key: str
    label: str
    align: str = "left"
    is_amount: bool = False


def parse_report_filters(request):
    per_page = request.GET.get("per_page", "50")
    if per_page not in {"25", "50", "100", "200"}:
        per_page = "50"
    return {
        "start_date": _parse_date(request.GET.get("start_date")),
        "end_date": _parse_date(request.GET.get("end_date")),
        "status": request.GET.get("status", "").strip(),
        "client": request.GET.get("client", "").strip(),
        "loan_product": request.GET.get("loan_product", "").strip(),
        "loan_officer": request.GET.get("loan_officer", "").strip(),
        "q": request.GET.get("q", "").strip(),
        "per_page": int(per_page),
        "export": request.GET.get("export", "").strip().lower(),
    }


def filtered_loans(filters, *, date_field="disbursement_date") -> QuerySet:
    qs = (
        Loan.objects.select_related("borrower", "account", "applied_by")
        .prefetch_related("repayments", "penalties")
        .order_by(date_field, "id")
    )
    start_date = filters.get("start_date")
    end_date = filters.get("end_date")
    status = filters.get("status")
    client = filters.get("client")
    loan_product = filters.get("loan_product")
    loan_officer = filters.get("loan_officer")
    search = filters.get("q")

    if start_date:
        qs = qs.filter(**{f"{date_field}__gte": start_date})
    if end_date:
        qs = qs.filter(**{f"{date_field}__lte": end_date})
    if status:
        qs = qs.filter(status=status)
    if client:
        qs = qs.filter(borrower_id=client)
    if loan_product:
        qs = qs.filter(loan_purpose=loan_product)
    if loan_officer:
        qs = qs.filter(applied_by_id=loan_officer)
    if search:
        qs = qs.filter(
            Q(id__icontains=search)
            | Q(borrower__full_name__icontains=search)
            | Q(applied_by__username__icontains=search)
        )
    return qs


def loan_financial_row(loan: Loan, today: date | None = None) -> dict:
    today = today or timezone.localdate()
    repayments = [repayment for repayment in loan.repayments.all() if repayment.repayment_date <= today]
    penalties = list(loan.penalties.all())
    balances = remaining_balances_from_related(loan, repayments, penalties)
    balances["penalty_balance"] = penalty_balance_as_of(repayments, penalties, today)
    paid_principal = sum((r.principal_payment for r in repayments), Decimal("0.00"))
    paid_interest = sum((r.interest_payment for r in repayments), Decimal("0.00"))
    paid_penalties = sum((r.penalty_payment for r in repayments), Decimal("0.00"))
    total_paid = paid_principal + paid_interest + paid_penalties
    total_outstanding = sum(balances.values())
    arrears = installment_arrears(loan, today, paid_principal + paid_interest, total_outstanding)
    before = installment_arrears(loan, today - timedelta(days=1), paid_principal + paid_interest, total_outstanding)
    due_today = max(arrears["overdue_amount"] - before["overdue_amount"], Decimal("0.00"))
    last_repayment_date = max((r.repayment_date for r in repayments), default=None)

    return {
        "loan_id": loan.id,
        "borrower_id": loan.borrower_id,
        "gender": loan.borrower.gender or "Not recorded",
        "current_status": loan.status,
        "penalty_history_incomplete": any(p.is_deleted and not p.deleted_at for p in penalties),
        "client": loan.borrower.full_name,
        "reg_number": loan.borrower.reg_number or "",
        "loan_product": loan.get_loan_purpose_display(),
        "loan_officer": getattr(loan.applied_by, "username", "") or "-",
        "status": loan.get_status_display(),
        "application_date": loan.start_date,
        "disbursement_date": loan.disbursement_date,
        "maturity_date": loan.due_date,
        "principal": loan.principal_amount or Decimal("0.00"),
        "interest": loan.total_interest or Decimal("0.00"),
        "interest_rate": loan.interest_rate,
        "loan_period_months": loan.loan_period_months,
        "fees": Decimal("0.00"),
        "penalties": balances["penalty_balance"],
        "paid_principal": paid_principal,
        "paid_interest": paid_interest,
        "paid_penalties": paid_penalties,
        "paid_amount": total_paid,
        "outstanding_principal": balances["principal_balance"],
        "outstanding_interest": balances["interest_balance"],
        "outstanding_fees": Decimal("0.00"),
        "outstanding_penalties": balances["penalty_balance"],
        "outstanding_amount": total_outstanding,
        "overdue_amount": arrears["overdue_amount"],
        "days_in_arrears": arrears["days_in_arrears"],
        "aging_bucket": aging_bucket(arrears["days_in_arrears"]),
        "last_repayment_date": last_repayment_date,
        "expected_due": arrears["expected_due"],
        "installments_due": arrears["installments_due"],
        "due_on_date": due_today,
        "overdue_before_date": before["overdue_amount"],
        "relevant_due_date": today - timedelta(days=arrears["days_in_arrears"])
        if arrears["overdue_amount"] > 0
        else None,
    }


def penalty_balance_as_of(repayments, penalties, as_of):
    """Replay dated assessments, FIFO payments, and reversals through the cutoff."""
    events = []
    for penalty in penalties:
        if penalty.is_deleted and not penalty.deleted_at:
            # Legacy deletions without an effective date cannot be reconstructed.
            continue
        if penalty.penalty_date <= as_of:
            events.append((penalty.penalty_date, 0, penalty.pk, penalty.penalty_amount))
        if penalty.is_deleted and penalty.deleted_at:
            deleted_on = timezone.localtime(penalty.deleted_at).date()
            if deleted_on <= as_of:
                events.append((deleted_on, 2, penalty.pk, Decimal("0.00")))
    for repayment in repayments:
        if repayment.repayment_date <= as_of and repayment.penalty_payment > 0:
            events.append((repayment.repayment_date, 1, repayment.pk, repayment.penalty_payment))

    remaining = {}
    for _, kind, pk, amount in sorted(events):
        if kind == 0:
            remaining[pk] = amount
        elif kind == 2:
            remaining[pk] = Decimal("0.00")
        else:
            for penalty_id, balance in remaining.items():
                applied = min(balance, amount)
                remaining[penalty_id] -= applied
                amount -= applied
                if amount <= 0:
                    break
    return sum(remaining.values(), Decimal("0.00"))


@cached_report("loans")
def aging_report_rows(filters):
    """Select the disbursement cohort, then reconstruct its end-date exposure."""
    as_of = filters["end_date"]
    statuses = list(Loan.ACTIVE_STATUSES)
    if as_of < timezone.localdate():
        statuses.extend(["repaid", "closed"])
    loans = filtered_loans(filters).filter(
        disbursement_date__isnull=False,
        status__in=statuses,
    )
    # A loan repaid since the cutoff must still appear if it owed money then.
    rows = [loan_financial_row(loan, today=as_of) for loan in loans]
    return [row for row in rows if row["outstanding_amount"] > 0]


def aging_report_summary(rows):
    borrowers = {row["borrower_id"]: row.get("gender", "Not recorded") for row in rows}
    principal_total = sum((row["outstanding_principal"] for row in rows), Decimal("0.00"))
    principal_over_30 = sum(
        (row["outstanding_principal"] for row in rows if row["days_in_arrears"] > 30), Decimal("0.00")
    )
    return {
        "clients_in_arrears": len(
            {row["borrower_id"] for row in rows if row["days_in_arrears"] > 0 and row["overdue_amount"] > 0}
        ),
        "par_over_30_percent": principal_over_30 / principal_total * 100 if principal_total > 0 else Decimal("0"),
        "active_borrowers": len(borrowers),
        "non_performing_loans": sum(row["days_in_arrears"] >= 90 and row["outstanding_amount"] > 0 for row in rows),
        "female_borrowers": sum(gender == "Female" for gender in borrowers.values()),
        "male_borrowers": sum(gender == "Male" for gender in borrowers.values()),
        "unknown_gender_borrowers": sum(gender not in {"Female", "Male"} for gender in borrowers.values()),
        "principal_over_30": principal_over_30,
    }


@cached_report("loans")
def repayment_rows(filters) -> list[dict]:
    qs = LoanRepayment.objects.select_related("loan", "loan__borrower", "loan__applied_by", "account").order_by(
        "repayment_date", "id"
    )
    if filters.get("start_date"):
        qs = qs.filter(repayment_date__gte=filters["start_date"])
    if filters.get("end_date"):
        qs = qs.filter(repayment_date__lte=filters["end_date"])
    if filters.get("client"):
        qs = qs.filter(loan__borrower_id=filters["client"])
    if filters.get("loan_product"):
        qs = qs.filter(loan__loan_purpose=filters["loan_product"])
    if filters.get("loan_officer"):
        qs = qs.filter(loan__applied_by_id=filters["loan_officer"])
    if filters.get("status"):
        qs = qs.filter(loan__status=filters["status"])
    if filters.get("q"):
        search = filters["q"]
        qs = qs.filter(
            Q(loan_id__icontains=search)
            | Q(loan__borrower__full_name__icontains=search)
            | Q(loan__applied_by__username__icontains=search)
        )

    rows = []
    for repayment in qs:
        rows.append(
            {
                "loan_id": repayment.loan_id,
                "client": repayment.loan.borrower.full_name,
                "repayment_date": repayment.repayment_date,
                "principal": repayment.principal_payment,
                "interest": repayment.interest_payment,
                "fees": Decimal("0.00"),
                "penalties": repayment.penalty_payment,
                "paid_amount": repayment.total_payment,
                "account": repayment.account.account_name,
                "description": repayment.description or "",
            }
        )
    return rows


def remaining_balances_from_related(loan: Loan, repayments=None, penalties=None) -> dict:
    repayments = list(repayments if repayments is not None else loan.repayments.all())
    penalties = list(penalties if penalties is not None else loan.penalties.all())
    paid_principal = sum((r.principal_payment for r in repayments), Decimal("0.00"))
    paid_interest = sum((r.interest_payment for r in repayments), Decimal("0.00"))
    unpaid_penalties = sum(
        (p.remaining_amount for p in penalties if not p.is_paid and not getattr(p, "is_deleted", False)),
        Decimal("0.00"),
    )
    return {
        "principal_balance": max((loan.principal_amount or Decimal("0.00")) - paid_principal, Decimal("0.00")),
        "interest_balance": max((loan.total_interest or Decimal("0.00")) - paid_interest, Decimal("0.00")),
        "penalty_balance": max(unpaid_penalties, Decimal("0.00")),
    }


def installment_arrears(
    loan: Loan,
    today: date,
    paid_principal_interest: Decimal,
    outstanding: Decimal,
) -> dict:
    """Unpaid scheduled P&I through today, allocating payments oldest-first.

    Includes today's installment so Due reports can split it from past arrears.
    Loan Aging displays the separately calculated overdue_before_date amount.
    """
    if outstanding <= 0 or not loan.disbursement_date or not loan.loan_period_months:
        return {
            "days_in_arrears": 0,
            "overdue_amount": Decimal("0.00"),
            "expected_due": Decimal("0.00"),
            "installments_due": 0,
        }

    term_months = int(loan.loan_period_months)
    cumulative_due = Decimal("0.00")
    interest_due = Decimal("0.00")
    first_unpaid_due_date = None
    installments_due = 0
    for month in range(1, term_months + 1):
        due_date = loan.disbursement_date + relativedelta(months=month)
        if due_date > today:
            break
        installments_due = month
        if month == term_months:
            # Settle the stored contractual balance, including rounding remainders.
            cumulative_due = loan.total_repayable
        elif loan.interest_method == "reducing_rate":
            monthly_principal = loan.principal_amount / Decimal(term_months)
            opening_principal = loan.principal_amount - monthly_principal * (month - 1)
            monthly_rate = Decimal(loan.interest_rate) / Decimal("1200")
            interest_due += (opening_principal * monthly_rate).quantize(
                Decimal("0.01"), rounding=ROUND_DOWN
            )
            principal_due = (monthly_principal * month).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cumulative_due = min(
                principal_due + min(interest_due, loan.total_interest or Decimal("0")),
                loan.total_repayable,
            )
        else:
            cumulative_due = min(loan.monthly_installment * month, loan.total_repayable)
        if first_unpaid_due_date is None and paid_principal_interest < cumulative_due:
            first_unpaid_due_date = due_date

    expected_due = cumulative_due
    overdue_amount = max(expected_due - paid_principal_interest, Decimal("0.00"))
    if first_unpaid_due_date is None:
        return {
            "days_in_arrears": 0,
            "overdue_amount": overdue_amount,
            "expected_due": expected_due,
            "installments_due": installments_due,
        }

    return {
        "days_in_arrears": max((today - first_unpaid_due_date).days, 0),
        "overdue_amount": overdue_amount,
        "expected_due": expected_due,
        "installments_due": installments_due,
    }


def paginate_rows(rows: list[dict], page_number, per_page: int):
    paginator = Paginator(rows, per_page)
    return paginator.get_page(page_number)


def summarize_amounts(rows: Iterable[dict], keys: Iterable[str]) -> dict:
    totals = {key: Decimal("0.00") for key in keys}
    count = 0
    for row in rows:
        count += 1
        for key in totals:
            totals[key] += row.get(key) or Decimal("0.00")
    totals["count"] = count
    return totals


def group_rows_by_bucket(rows: Iterable[dict], bucket_key: str, total_keys: Iterable[str]) -> list[dict]:
    groups = {}
    for row in rows:
        bucket = row.get(bucket_key) or "Unclassified"
        groups.setdefault(bucket, []).append(row)

    return [
        {
            "key": bucket,
            "rows": groups[bucket],
            "totals": summarize_amounts(groups[bucket], total_keys),
        }
        for bucket in sorted(groups, key=_bucket_order)
    ]


def portfolio_at_risk_summary(rows: Iterable[dict]) -> dict:
    portfolio_rows = [row for row in rows if (row.get("outstanding_amount") or Decimal("0.00")) > 0]
    total_portfolio = sum(
        (row["outstanding_amount"] for row in portfolio_rows),
        Decimal("0.00"),
    )
    bands = []
    for label, minimum_days in PAR_THRESHOLDS:
        affected = [row for row in portfolio_rows if int(row.get("days_in_arrears") or 0) >= minimum_days]
        outstanding = sum(
            (row["outstanding_amount"] for row in affected),
            Decimal("0.00"),
        )
        percent = outstanding / total_portfolio * Decimal("100") if total_portfolio else Decimal("0.00")
        bands.append(
            {
                "bucket": label,
                "minimum_days": minimum_days,
                "loan_count": len(affected),
                "outstanding_amount": outstanding,
                "portfolio_percent": percent,
            }
        )
    return {
        "total_portfolio": total_portfolio,
        "loan_count": len(portfolio_rows),
        "bands": bands,
    }


def aging_bucket(days: int) -> str:
    if days <= 0:
        return "Current"
    if days <= 30:
        return "1-30 days overdue"
    if days <= 60:
        return "31-60 days overdue"
    if days <= 90:
        return "61-90 days overdue"
    if days <= 180:
        return "91-180 days overdue"
    return "Over 180 days overdue"


def _bucket_order(bucket: str):
    standard_order = {label: index for index, label in enumerate(STANDARD_AGING_BUCKETS)}
    category_order = {
        "Due today": 0,
        "Due on selected date": 0,
        "In arrears": 1,
        "Past maturity": 2,
        "Current": 3,
        "Unclassified": 99,
    }
    if bucket in standard_order:
        return (0, standard_order[bucket], bucket)
    if bucket in category_order:
        return (1, category_order[bucket], bucket)
    return (2, 0, bucket)


def export_rows_csv(filename: str, columns: list[ReportColumn], rows: list[dict]) -> HttpResponse:
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow([column.label for column in columns])
    for row in rows:
        writer.writerow([_csv_value(row.get(column.key)) for column in columns])
    return response


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _days_in_arrears(loan: Loan, today: date, outstanding: Decimal) -> int:
    if outstanding <= 0 or not loan.due_date:
        return 0
    return max((today - loan.due_date).days, 0)


def _csv_value(value):
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    return value
