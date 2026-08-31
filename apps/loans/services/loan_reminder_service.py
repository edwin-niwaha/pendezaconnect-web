from datetime import date
from decimal import Decimal
from typing import Dict, Optional

from apps.loans.models import Loan
from apps.loans.services.aging import compute_installment_based_days_overdue


class LoanReminderService:
    """
    Builds borrower-facing reminder data for active loans.

    The service intentionally returns only actionable values needed by email,
    while the model remains the source of truth for balances and schedules.
    """

    def __init__(self, loan: Loan, today: date, pre_due_days: int = 7):
        self.loan = loan
        self.today = today
        self.pre_due_days = pre_due_days

    def get_info(self) -> Optional[Dict]:
        if not self.loan.is_active_for_reporting():
            return None

        balances = self.loan.report_balances()
        total_outstanding = balances["total_outstanding"]

        if total_outstanding <= Decimal("0.00"):
            return None

        schedule = self.loan.generate_payment_schedule()
        if not schedule:
            return None

        today_installments = [payment for payment in schedule if payment["payment_due_date"] == self.today]

        if today_installments:
            expected = sum(payment["total_payment"] for payment in today_installments)
            amount_due = self.loan.calculate_total_amount_due_balance(
                self.today,
                expected,
            )
            if amount_due > 0:
                return {
                    "category": "due_today",
                    "notice_title": "Payment due today",
                    "action_label": "Amount due today",
                    "action_amount": min(amount_due, total_outstanding),
                    "payment_due_date": self.today,
                    **balances,
                }

        upcoming = [
            payment
            for payment in schedule
            if payment["payment_due_date"] > self.today
            and 0 < (payment["payment_due_date"] - self.today).days <= self.pre_due_days
        ]

        if upcoming:
            next_payment = min(upcoming, key=lambda payment: payment["payment_due_date"])
            return {
                "category": "pre_due",
                "notice_title": "Upcoming loan payment",
                "action_label": "Next installment",
                "action_amount": min(next_payment["total_payment"], total_outstanding),
                "days_until": (next_payment["payment_due_date"] - self.today).days,
                "payment_due_date": next_payment["payment_due_date"],
                **balances,
            }

        missed = [payment for payment in schedule if payment["payment_due_date"] < self.today]

        if missed:
            aging = compute_installment_based_days_overdue(self.loan, self.today)
            first_unpaid_due_date = aging["first_unpaid_due_date"]
            amount_overdue = aging["shortfall"]

            if first_unpaid_due_date and amount_overdue > 0:
                return {
                    "category": "overdue",
                    "notice_title": "Overdue loan payment",
                    "action_label": "Overdue amount",
                    "action_amount": min(amount_overdue, total_outstanding),
                    "days_overdue": aging["days_overdue"],
                    "payment_due_date": first_unpaid_due_date,
                    **balances,
                }

        if self.loan.due_date and self.loan.due_date < self.today:
            return {
                "category": "overdue",
                "notice_title": "Overdue loan payment",
                "action_label": "Outstanding balance",
                "action_amount": total_outstanding,
                "days_overdue": (self.today - self.loan.due_date).days,
                "payment_due_date": self.loan.due_date,
                **balances,
            }

        return None
