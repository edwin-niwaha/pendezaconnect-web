from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.db.models import Sum

from apps.loans.models import Loan


def compute_installment_based_days_overdue(loan: Loan, today: date) -> dict:
    """
    Installment-based aging. Uses loan.monthly_installment so reports and
    notifications calculate overdue days from the same repayment coverage.
    """
    disbursement_date = loan.disbursement_date
    term_months = loan.loan_period_months

    empty = {
        "days_overdue": 0,
        "next_due_date": None,
        "final_due_date": None,
        "monthly_installment": Decimal("0.00"),
        "total_repayable": Decimal("0.00"),
        "installments_due_by_now": 0,
        "total_due_by_today": Decimal("0.00"),
        "total_paid_pi": Decimal("0.00"),
        "shortfall": Decimal("0.00"),
        "first_unpaid_due_date": None,
    }

    if not disbursement_date or not term_months or term_months <= 0:
        if loan.due_date:
            days_overdue = max((today - loan.due_date).days, 0)
            return {
                **empty,
                "days_overdue": days_overdue,
                "next_due_date": loan.due_date if days_overdue > 0 else None,
                "final_due_date": loan.due_date,
            }
        return empty

    total_repayable = loan.total_repayable
    monthly_installment = loan.monthly_installment
    final_due_date = disbursement_date + relativedelta(months=term_months)

    paid = loan.repayments.filter(repayment_date__lte=today).aggregate(
        total_principal=Sum("principal_payment"),
        total_interest=Sum("interest_payment"),
    )
    total_paid_pi = (paid["total_principal"] or Decimal("0.00")) + (paid["total_interest"] or Decimal("0.00"))

    installments_due_by_now = sum(
        1 for n in range(1, term_months + 1) if disbursement_date + relativedelta(months=n) <= today
    )

    if installments_due_by_now == 0:
        return {
            **empty,
            "next_due_date": disbursement_date + relativedelta(months=1),
            "final_due_date": final_due_date,
            "monthly_installment": monthly_installment,
            "total_repayable": total_repayable,
            "total_paid_pi": total_paid_pi,
        }

    total_due_by_today = (monthly_installment * installments_due_by_now).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )

    first_unpaid_due_date = None
    for n in range(1, installments_due_by_now + 1):
        cumulative_due = (monthly_installment * n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_paid_pi + Decimal("0.01") < cumulative_due:
            first_unpaid_due_date = disbursement_date + relativedelta(months=n)
            break

    if first_unpaid_due_date is None:
        next_installment_no = installments_due_by_now + 1
        next_due_date = (
            disbursement_date + relativedelta(months=next_installment_no)
            if next_installment_no <= term_months
            else None
        )
        return {
            **empty,
            "next_due_date": next_due_date,
            "final_due_date": final_due_date,
            "monthly_installment": monthly_installment,
            "total_repayable": total_repayable,
            "installments_due_by_now": installments_due_by_now,
            "total_due_by_today": total_due_by_today,
            "total_paid_pi": total_paid_pi,
        }

    shortfall = (total_due_by_today - total_paid_pi).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    days_overdue = max((today - first_unpaid_due_date).days, 0)

    return {
        "days_overdue": days_overdue,
        "next_due_date": first_unpaid_due_date,
        "final_due_date": final_due_date,
        "monthly_installment": monthly_installment,
        "total_repayable": total_repayable,
        "installments_due_by_now": installments_due_by_now,
        "total_due_by_today": total_due_by_today,
        "total_paid_pi": total_paid_pi,
        "shortfall": shortfall,
        "first_unpaid_due_date": first_unpaid_due_date,
    }
