import csv
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.client.models import Client

from . import test_aging_report
from .risk_reports import principal_risk_bands


class RiskReportTests(TestCase):
    setUp = test_aging_report.AgingReportTests.setUp
    loan = test_aging_report.AgingReportTests.loan
    payment = test_aging_report.AgingReportTests.payment
    penalty = test_aging_report.AgingReportTests.penalty
    names = (
        "loan-arrears-report",
        "portfolio_at_risk_report",
        "non_performing_loans",
        "due_overdue_report",
        "defaulted_loans_report",
        "outstanding_balances_report",
    )

    def get_report(self, name, **query):
        return self.client.get(reverse("loans:" + name), {"end_date": "2026-05-02", **query})

    def test_all_reports_validate_before_export(self):
        for name in self.names:
            for query in ({"end_date": "bad"}, {"start_date": "2026-06-01"}, {"end_date": "2999-01-01"}):
                response = self.get_report(name, export="csv", **query)
                self.assertEqual(response.status_code, 400)
                self.assertNotContains(response, 'aria-label="Report totals"', status_code=400)

    def test_cutoff_historical_repayment_and_npl_match_aging(self):
        loan = self.loan(status="repaid")
        self.payment(loan, date(2026, 5, 3), principal="1000", interest="100")
        for name in ("loan-arrears-report", "non_performing_loans", "due_overdue_report"):
            response = self.get_report(name)
            self.assertEqual(response.context["totals"]["count"], 1)
            self.assertEqual(self.get_report(name, end_date="2026-05-03").context["totals"]["count"], 0)
        aging = self.get_report("loan_aging_report")
        npl = self.get_report("non_performing_loans")
        self.assertEqual(npl.context["totals"]["count"], aging.context["aging_summary"]["non_performing_loans"])
        self.assertEqual(self.get_report("non_performing_loans", end_date="2026-05-01").context["totals"]["count"], 0)

    def test_par_matches_aging_and_does_not_sum_overlapping_rows(self):
        self.loan()
        self.loan(principal_amount=Decimal("3000"), disbursement_date=date(2026, 5, 1))
        response = self.get_report("portfolio_at_risk_report")
        aging = self.get_report("loan_aging_report")
        band = response.context["all_rows"][1]
        self.assertEqual(band["principal_at_risk"], aging.context["aging_summary"]["principal_over_30"])
        self.assertEqual(band["par_percent"], "25.00%")
        self.assertNotContains(response, "<tfoot>")
        self.assertContains(response, "Risk thresholds")
        self.assertContains(response, "Portfolio loans")
        self.assertNotContains(response, "Arrears selection")

    def test_search_disbursement_range_and_distinct_clients(self):
        self.loan()
        self.loan()
        other = Client.objects.create(full_name="New Borrower", gender="Female")
        self.loan(borrower=other, disbursement_date=date(2026, 2, 1))
        response = self.get_report("loan-arrears-report")
        cards = {c["label"]: c["value"] for c in response.context["summary_cards"]}
        self.assertEqual(cards["Overdue loans"], 3)
        self.assertEqual(cards["Clients in arrears"], 2)
        for name in self.names:
            response = self.get_report(name, start_date="2026-02-01", q="New Borrower")
            if name == "portfolio_at_risk_report":
                self.assertEqual(response.context["summary_cards"][0]["value"], 1)
            elif name in ("non_performing_loans", "defaulted_loans_report"):
                self.assertEqual(response.context["totals"]["count"], 0)
            else:
                self.assertEqual(response.context["totals"]["count"], 1)

    def test_due_today_is_not_arrears_and_partial_payment_is_allocated(self):
        loan = self.loan()
        self.payment(loan, date(2026, 3, 1), principal="130", interest="20")
        response = self.get_report("due_overdue_report", end_date="2026-03-01")
        row = response.context["all_rows"][0]
        self.assertEqual(row["category"], "Due on selected date")
        self.assertEqual(row["overdue_before_date"], Decimal("0"))
        self.assertEqual(row["due_on_date"], Decimal("70"))
        self.assertEqual(self.get_report("loan-arrears-report", end_date="2026-03-01").context["totals"]["count"], 0)
        self.payment(loan, date(2026, 3, 1), principal="70")
        self.assertEqual(self.get_report("due_overdue_report", end_date="2026-03-01").context["totals"]["count"], 0)

    def test_due_and_overdue_split_without_double_counting(self):
        self.loan()
        response = self.get_report("due_overdue_report", end_date="2026-03-01")
        row = response.context["all_rows"][0]
        self.assertEqual(row["category"], "In arrears")
        self.assertEqual(row["overdue_before_date"], Decimal("110"))
        self.assertEqual(row["due_on_date"], Decimal("110"))
        self.assertEqual(response.context["totals"]["count"], 1)

    def test_past_maturity_includes_penalty_only_balance(self):
        loan = self.loan(due_date=date(2026, 4, 1))
        self.payment(loan, date(2026, 4, 1), principal="1000", interest="100")
        self.penalty(loan, date(2026, 4, 2), amount="50")
        response = self.get_report("due_overdue_report")
        row = response.context["all_rows"][0]
        self.assertEqual(row["category"], "Past maturity")
        self.assertEqual(row["outstanding_amount"], Decimal("50"))
        self.assertEqual(row["due_on_date"] + row["overdue_before_date"], Decimal("0"))

    def test_export_and_print_context(self):
        self.loan(disbursement_date=date(2025, 12, 31))
        for name in self.names:
            response = self.get_report(name)
            exported = self.get_report(name, export="csv")
            data = list(csv.DictReader(StringIO(exported.content.decode())))
            self.assertEqual(len(data), len(response.context["all_rows"]))
            self.assertContains(response, 'class="aging-print-context">As of 02/05/2026')
            if name != "portfolio_at_risk_report":
                self.assertEqual(data[0]["Total Balance"], "1100.00")
                self.assertContains(
                    response, reverse("loans:loan_detail", args=[response.context["all_rows"][0]["loan_id"]])
                )

    def test_empty_and_zero_principal_par_and_thresholds(self):
        for name in self.names:
            self.assertEqual(self.get_report(name).status_code, 200)
        row = {"borrower_id": 1, "outstanding_principal": Decimal("100"), "days_in_arrears": 30}
        self.assertEqual(principal_risk_bands([row])[1]["par_percent"], "0.00%")
        row["days_in_arrears"] = 31
        self.assertEqual(principal_risk_bands([row])[1]["par_percent"], "100.00%")
        row["days_in_arrears"] = 90
        self.assertEqual(principal_risk_bands([row])[3]["par_percent"], "0.00%")
        row["days_in_arrears"] = 91
        self.assertEqual(principal_risk_bands([row])[3]["par_percent"], "100.00%")
        row["outstanding_principal"] = Decimal("0")
        self.assertEqual(principal_risk_bands([row])[3]["par_percent"], "0.00%")

    def test_old_due_date_parameter_is_not_silently_used(self):
        self.assertEqual(self.get_report("due_overdue_report", date="2026-01-01").status_code, 400)

    def test_defaulted_strict_boundary_and_historical_payment(self):
        loan = self.loan(status="repaid")
        self.payment(loan, date(2026, 5, 4), principal="1000", interest="100")
        for cutoff, expected in (("2026-05-02", 0), ("2026-05-03", 1), ("2026-05-04", 0)):
            response = self.get_report("defaulted_loans_report", end_date=cutoff)
            self.assertEqual(response.context["totals"]["count"], expected)
        self.assertEqual(self.get_report("non_performing_loans").context["totals"]["count"], 1)

    def test_outstanding_includes_current_and_penalty_only_not_undisbursed(self):
        self.loan(disbursement_date=date(2026, 5, 1))
        loan = self.loan()
        self.payment(loan, date(2026, 4, 1), principal="1000", interest="100")
        self.penalty(loan, date(2026, 4, 2), amount="50")
        self.loan(status="approved", disbursement_date=None)
        self.loan(status="repaid")
        with patch("django.utils.timezone.localdate", return_value=date(2026, 5, 2)):
            response = self.get_report("outstanding_balances_report")
        self.assertEqual(response.context["totals"]["count"], 2)
        self.assertEqual(response.context["totals"]["outstanding_amount"], Decimal("1150"))
        cards = {c["label"]: c["value"] for c in response.context["summary_cards"]}
        self.assertEqual(cards["Active clients"], 1)
        self.assertEqual(cards["Interest balance"], Decimal("100"))
        self.assertEqual(cards["Penalties"], Decimal("50"))
        self.assertEqual(cards["Overdue"], Decimal("0"))
