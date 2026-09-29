import csv
from datetime import date, datetime
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.client.models import Client
from apps.users.models import Profile

from .forms import LoanAgingReportFilterForm
from .models import ChartOfAccounts, Loan, LoanPenalty, LoanRepayment
from .services.reporting import aging_report_rows, aging_report_summary, loan_financial_row


# These accounting fixtures use bulk writes, which intentionally bypass signals.
# Cache lifecycle is covered separately by dashboard.test_report_cache.
@override_settings(REPORT_CACHE_TTL=0)
class AgingReportTests(TestCase):
    def setUp(self):
        self.borrower = Client.objects.create(full_name="Aging Client", reg_number="AGING-1")
        self.account = ChartOfAccounts.objects.create(account_name="Cash", account_type="asset", account_number="1010")
        self.user = User.objects.create_user(username="aging-manager")
        Profile.objects.create(user=self.user, role="manager")
        self.client.force_login(self.user)
        self.url = reverse("loans:loan_aging_report")

    def loan(self, **overrides):
        values = {
            "borrower": self.borrower,
            "principal_amount": Decimal("1000.00"),
            "total_interest": Decimal("100.00"),
            "interest_rate": Decimal("10.00"),
            "loan_period_months": 10,
            "start_date": date(2025, 12, 1),
            "disbursement_date": date(2026, 1, 1),
            "due_date": date(2026, 11, 1),
            "status": "disbursed",
        }
        values.update(overrides)
        # Reporting fixtures deliberately avoid posting journals or notifications.
        return Loan.objects.bulk_create([Loan(**values)])[0]

    def payment(self, loan, on, principal="0", interest="0", penalty="0"):
        return LoanRepayment.objects.bulk_create([
            LoanRepayment(
                loan=loan, account=self.account, repayment_date=on,
                principal_payment=Decimal(principal), interest_payment=Decimal(interest),
                penalty_payment=Decimal(penalty),
            )
        ])[0]

    def penalty(self, loan, on, amount="100", **overrides):
        values = dict(
            loan=loan, account=self.account, penalty_date=on,
            penalty_amount=Decimal(amount), remaining_amount=Decimal(amount), reason="Test penalty",
        )
        values.update(overrides)
        return LoanPenalty.objects.bulk_create([LoanPenalty(**values)])[0]

    def test_balances_and_last_payment_exclude_later_repayments(self):
        loan = self.loan()
        self.payment(loan, date(2026, 2, 1), principal="100", interest="10")
        self.payment(loan, date(2026, 4, 1), principal="900", interest="90")
        row = loan_financial_row(loan, today=date(2026, 3, 3))
        self.assertEqual(row["outstanding_principal"], Decimal("900"))
        self.assertEqual(row["outstanding_interest"], Decimal("90"))
        self.assertEqual(row["paid_amount"], Decimal("110"))
        self.assertEqual(row["last_repayment_date"], date(2026, 2, 1))
        self.assertEqual(row["overdue_amount"], Decimal("110"))
        self.assertEqual(row["days_in_arrears"], 2)

    def test_repayments_on_cutoff_are_included(self):
        loan = self.loan()
        self.payment(loan, date(2026, 3, 3), principal="250")
        row = loan_financial_row(loan, today=date(2026, 3, 3))
        self.assertEqual(row["outstanding_principal"], Decimal("750"))
        self.assertEqual(row["days_in_arrears"], 0)

    def test_disbursement_period_includes_both_boundaries(self):
        before = self.loan(disbursement_date=date(2025, 12, 31))
        first = self.loan()
        last = self.loan(disbursement_date=date(2026, 3, 3))
        self.loan(disbursement_date=date(2026, 3, 4))
        self.loan(disbursement_date=None, status="approved")
        self.loan(status="rejected")
        rows = aging_report_rows({"start_date": date(2026, 1, 1), "end_date": date(2026, 3, 3)})
        self.assertEqual({row["loan_id"] for row in rows}, {first.pk, last.pk})
        all_rows = aging_report_rows({"end_date": date(2026, 3, 3)})
        self.assertEqual({row["loan_id"] for row in all_rows}, {before.pk, first.pk, last.pk})

    def test_repaid_loan_appears_before_its_final_payment(self):
        loan = self.loan(status="repaid")
        self.payment(loan, date(2026, 4, 1), principal="1000", interest="100")
        rows = aging_report_rows({"end_date": date(2026, 3, 3)})
        self.assertEqual([row["loan_id"] for row in rows], [loan.pk])
        self.assertEqual(aging_report_rows({"end_date": date(2026, 4, 1)}), [])

    def test_borrower_count_is_distinct_by_id_not_name_or_loan_count(self):
        self.loan()
        self.loan()
        other = Client.objects.create(full_name="Aging Client", reg_number="AGING-2")
        self.loan(borrower=other)
        summary = aging_report_summary(aging_report_rows({"end_date": date(2026, 3, 3)}))
        self.assertEqual(summary["active_borrowers"], 2)

    def test_today_counts_only_running_loans_with_a_balance(self):
        active = self.loan()
        self.loan(status="closed")
        self.loan(status="repaid")
        with patch("django.utils.timezone.localdate", return_value=date(2026, 3, 3)):
            rows = aging_report_rows({"end_date": date(2026, 3, 3)})
        self.assertEqual([row["loan_id"] for row in rows], [active.pk])

    def test_historical_closed_loans_show_missing_closure_history_warning(self):
        self.loan(status="closed")
        response = self.client.get(self.url, {"end_date": "2026-03-03"})
        self.assertContains(response, "Closure dates are not stored")

    def test_over_30_is_strict_and_sums_principal_not_total_debt(self):
        thirty = self.loan()
        thirty_one = self.loan(disbursement_date=date(2025, 12, 31))
        rows = aging_report_rows({"end_date": date(2026, 3, 3)})
        by_id = {row["loan_id"]: row for row in rows}
        self.assertEqual(by_id[thirty.pk]["days_in_arrears"], 30)
        self.assertEqual(by_id[thirty_one.pk]["days_in_arrears"], 31)
        self.assertEqual(aging_report_summary(rows)["principal_over_30"], Decimal("1000"))

    def test_partial_installment_keeps_oldest_unpaid_due_date(self):
        loan = self.loan()
        self.payment(loan, date(2026, 2, 1), principal="50")
        row = loan_financial_row(loan, today=date(2026, 3, 3))
        self.assertEqual(row["days_in_arrears"], 30)
        self.assertEqual(row["overdue_amount"], Decimal("170"))

    def test_final_installment_includes_rounding_remainder(self):
        loan = self.loan(total_interest=Decimal("0"), loan_period_months=3)
        self.payment(loan, date(2026, 4, 1), principal="999.99")
        row = loan_financial_row(loan, today=date(2026, 4, 2))
        self.assertEqual(row["expected_due"], Decimal("1000"))
        self.assertEqual(row["overdue_amount"], Decimal("0.01"))
        self.assertEqual(row["days_in_arrears"], 1)

    def test_penalties_use_assessment_and_payment_dates_not_current_balance(self):
        loan = self.loan()
        self.penalty(loan, date(2026, 2, 1), is_paid=True, remaining_amount=Decimal("0"))
        self.penalty(loan, date(2026, 4, 1), amount="200")
        self.payment(loan, date(2026, 2, 15), penalty="25")
        self.payment(loan, date(2026, 4, 1), penalty="75")
        self.assertEqual(loan_financial_row(loan, today=date(2026, 3, 3))["outstanding_penalties"], Decimal("75"))
        self.assertEqual(loan_financial_row(loan, today=date(2026, 4, 1))["outstanding_penalties"], Decimal("200"))

    def test_reversal_only_removes_unpaid_penalty_from_reversal_date(self):
        loan = self.loan()
        self.penalty(
            loan, date(2026, 2, 1), is_deleted=True, remaining_amount=Decimal("0"),
            deleted_at=timezone.make_aware(datetime(2026, 3, 1, 12)),
        )
        self.payment(loan, date(2026, 2, 15), penalty="40")
        self.assertEqual(loan_financial_row(loan, today=date(2026, 2, 28))["outstanding_penalties"], Decimal("60"))
        self.assertEqual(loan_financial_row(loan, today=date(2026, 3, 1))["outstanding_penalties"], Decimal("0"))

    def test_reversed_penalty_payments_do_not_reduce_later_assessments(self):
        loan = self.loan()
        self.penalty(
            loan, date(2026, 1, 2), is_deleted=True,
            deleted_at=timezone.make_aware(datetime(2026, 2, 1, 12)),
        )
        self.payment(loan, date(2026, 1, 15), penalty="40")
        self.penalty(loan, date(2026, 3, 1), amount="200")
        self.assertEqual(loan_financial_row(loan, today=date(2026, 3, 3))["outstanding_penalties"], Decimal("200"))

    def test_invalid_date_filters_do_not_calculate_or_export(self):
        for query in (
            {"end_date": "not-a-date"},
            {"start_date": "2026-04-01", "end_date": "2026-03-01"},
            {"end_date": "2999-01-01"},
            {"arrears_over": "invalid"},
        ):
            with self.subTest(query=query), patch("apps.loans.views.aging_report_rows") as build:
                response = self.client.get(self.url, {**query, "export": "csv"})
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, "Correct the filters", status_code=400)
                self.assertNotContains(response, 'aria-label="Report totals"', status_code=400)
                build.assert_not_called()

    def test_blank_end_date_defaults_to_today(self):
        with patch("django.utils.timezone.localdate", return_value=date(2026, 3, 3)):
            form = LoanAgingReportFilterForm({})
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.cleaned_data["end_date"], date(2026, 3, 3))

    def test_aging_selection_and_export_use_same_cutoff_and_totals(self):
        self.loan()
        older = self.loan(disbursement_date=date(2025, 12, 31))
        self.payment(older, date(2026, 4, 1), principal="1000", interest="100")
        query = {"end_date": "2026-03-03", "arrears_over": "30"}
        response = self.client.get(self.url, query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["totals"]["count"], 1)
        self.assertEqual(response.context["totals"]["outstanding_principal"], Decimal("1000"))
        self.assertEqual(response.context["aging_summary"]["active_borrowers"], 1)
        self.assertEqual(response.context["aging_summary"]["principal_over_30"], Decimal("1000"))
        self.assertEqual(response.context["all_rows"][0]["loan_id"], older.pk)
        exported = self.client.get(self.url, {**query, "export": "csv"})
        data = list(csv.DictReader(StringIO(exported.content.decode())))
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["Principal Bal."], "1000.00")
        self.assertEqual(data[0]["Disbursed On"], "31/12/2025")

    def test_search_applies_to_borrower_counts_and_amounts(self):
        self.loan()
        other = Client.objects.create(full_name="Other Borrower", reg_number="AGING-2")
        self.loan(borrower=other)
        response = self.client.get(self.url, {"end_date": "2026-03-03", "q": "Other Borrower"})
        self.assertEqual(response.context["totals"]["count"], 1)
        self.assertEqual(response.context["aging_summary"]["active_borrowers"], 1)
        self.assertEqual(response.context["totals"]["outstanding_principal"], Decimal("1000"))

    def test_empty_cohort_returns_zero_indicators(self):
        response = self.client.get(self.url, {"end_date": "2026-03-03"})
        self.assertEqual(response.context["aging_summary"], {
            "active_borrowers": 0, "female_borrowers": 0, "male_borrowers": 0,
            "clients_in_arrears": 0, "par_over_30_percent": Decimal("0"),
            "unknown_gender_borrowers": 0, "principal_over_30": Decimal("0"), "non_performing_loans": 0,
        })
        self.assertEqual(response.context["totals"]["count"], 0)

    def test_gender_counts_are_distinct_and_exported(self):
        self.borrower.gender = "Female"
        self.borrower.save(update_fields=["gender"])
        self.loan()
        self.loan()
        male = Client.objects.create(full_name="Male Client", gender="Male")
        unknown = Client.objects.create(full_name="Unknown Client")
        self.loan(borrower=male)
        self.loan(borrower=unknown)
        query = {"end_date": "2026-03-03"}
        response = self.client.get(self.url, query)
        summary = response.context["aging_summary"]
        self.assertEqual(summary["active_borrowers"], 3)
        self.assertEqual(summary["female_borrowers"], 1)
        self.assertEqual(summary["male_borrowers"], 1)
        self.assertEqual(summary["unknown_gender_borrowers"], 1)
        self.assertContains(response, "Gender</th>")
        exported = self.client.get(self.url, {**query, "export": "csv"})
        data = list(csv.DictReader(StringIO(exported.content.decode())))
        self.assertEqual(sorted(row["Gender"] for row in data), ["Female", "Female", "Male", "Not recorded"])
        filtered = self.client.get(self.url, {**query, "q": "Male Client"})
        self.assertEqual(filtered.context["aging_summary"]["active_borrowers"], 1)
        self.assertEqual(filtered.context["aging_summary"]["female_borrowers"], 0)
        self.assertEqual(filtered.context["aging_summary"]["male_borrowers"], 1)

    def test_non_performing_count_uses_cutoff_dates_and_search(self):
        # First unpaid instalment is 1 February: 89 days on 1 May, 90 on 2 May.
        first = self.loan()
        self.loan()
        other = Client.objects.create(full_name="Other Borrower", gender="Male")
        self.loan(borrower=other, disbursement_date=date(2026, 2, 1))
        self.payment(first, date(2026, 5, 3), principal="1000", interest="100")
        for end_date, expected in (("2026-05-01", 0), ("2026-05-02", 2), ("2026-05-03", 1)):
            with self.subTest(end_date=end_date):
                response = self.client.get(self.url, {"end_date": end_date})
                self.assertEqual(response.context["aging_summary"]["non_performing_loans"], expected)
                self.assertContains(response, "Non-performing loans (90+ days):")
        for extra in ({"start_date": "2026-02-01"}, {"q": "Other Borrower"}):
            response = self.client.get(self.url, {"end_date": "2026-05-02", **extra})
            self.assertEqual(response.context["aging_summary"]["non_performing_loans"], 0)
        response = self.client.get(self.url, {"end_date": "2026-05-02", "arrears_over": "30"})
        self.assertEqual(response.context["aging_summary"]["non_performing_loans"], 2)

    def test_par_and_distinct_clients_in_arrears_follow_filters(self):
        self.loan(disbursement_date=date(2025, 12, 31))
        self.loan(disbursement_date=date(2025, 12, 31))
        other = Client.objects.create(full_name="Current Borrower")
        self.loan(borrower=other, principal_amount=Decimal("2000"), disbursement_date=date(2026, 3, 1))
        query = {"end_date": "2026-03-03"}
        response = self.client.get(self.url, query)
        self.assertEqual(response.context["aging_summary"]["clients_in_arrears"], 1)
        self.assertEqual(response.context["aging_summary"]["par_over_30_percent"], Decimal("50"))
        self.assertContains(response, "50.00%")
        self.assertContains(response, 'class="aging-print-context">As of 03/03/2026')
        # The arrears table toggle must not shrink PAR's denominator to risky loans only.
        response = self.client.get(self.url, {**query, "arrears_over": "30"})
        self.assertEqual(response.context["aging_summary"]["par_over_30_percent"], Decimal("50"))
        for extra in ({"q": "Current Borrower"}, {"start_date": "2026-03-01"}):
            response = self.client.get(self.url, {**query, **extra})
            self.assertEqual(response.context["aging_summary"]["clients_in_arrears"], 0)
            self.assertEqual(response.context["aging_summary"]["par_over_30_percent"], Decimal("0"))

    def test_par_zero_principal_and_thirty_day_boundary(self):
        row = {
            "borrower_id": 1, "outstanding_principal": Decimal("100"),
            "days_in_arrears": 30, "overdue_amount": Decimal("10"), "outstanding_amount": Decimal("110"),
        }
        self.assertEqual(aging_report_summary([row])["par_over_30_percent"], Decimal("0"))
        row["days_in_arrears"] = 31
        self.assertEqual(aging_report_summary([row])["par_over_30_percent"], Decimal("100"))
        row["outstanding_principal"] = Decimal("0")
        summary = aging_report_summary([row])
        self.assertEqual(summary["par_over_30_percent"], Decimal("0"))
        self.assertEqual(summary["clients_in_arrears"], 1)
