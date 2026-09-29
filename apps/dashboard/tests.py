from datetime import date, datetime
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.loans import test_aging_report
from apps.loans.models import Loan, LoanDisbursement
from apps.loans.services.reporting import remaining_balances_from_related

from . import views


class LoansDashboardTests(TestCase):
    setUp = test_aging_report.AgingReportTests.setUp
    loan = test_aging_report.AgingReportTests.loan
    payment = test_aging_report.AgingReportTests.payment
    penalty = test_aging_report.AgingReportTests.penalty

    def populated_loan(self, **overrides):
        loan = self.loan(**overrides)
        self.payment(loan, date(2026, 2, 1), principal="20", interest="5", penalty="3")
        self.penalty(loan, date(2026, 2, 1), amount="10", remaining_amount=Decimal("7"))
        LoanDisbursement.objects.bulk_create([LoanDisbursement(loan=loan, account=self.account)])
        return loan

    @patch("apps.dashboard.views.timezone.now", return_value=timezone.make_aware(datetime(2026, 3, 1)))
    def test_cold_dashboard_query_count_does_not_grow_with_portfolio(self, now):
        self.populated_loan()
        with CaptureQueriesContext(connection) as small:
            context = views._build_loans_dashboard_context()
        self.assertEqual(context["disbursed_loans"], 1)
        for _ in range(24):
            self.populated_loan()
        with CaptureQueriesContext(connection) as large:
            context = views._build_loans_dashboard_context()
        self.assertEqual(context["disbursed_loans"], 25)
        self.assertEqual(len(large), len(small))
        self.assertLessEqual(len(large), 14)
        self.assertEqual(context["total_loans"]["total_principal_receivable"], Decimal("24500"))

    def test_prefetched_calculations_match_existing_model_rules(self):
        loan = self.populated_loan()
        self.payment(loan, date(2026, 4, 1), principal="30", interest="2")
        self.penalty(loan, date(2026, 2, 2), amount="9", is_paid=True)
        self.penalty(loan, date(2026, 2, 3), amount="8", is_deleted=True)
        self.penalty(loan, date(2026, 4, 1), amount="6")
        expected_balances = loan.calculate_remaining_balances()
        dates = [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]
        expected_due = [loan.calculate_total_amount_due_balance(day, Decimal("123.456")) for day in dates]
        prefetched = Loan.objects.prefetch_related("repayments", "penalties").get(pk=loan.pk)
        with self.assertNumQueries(0):
            self.assertEqual(remaining_balances_from_related(prefetched), expected_balances)
            self.assertEqual(
                [views._dashboard_due_balance(prefetched, day, Decimal("123.456")) for day in dates],
                expected_due,
            )

    @patch("apps.dashboard.views.timezone.now", return_value=timezone.make_aware(datetime(2026, 3, 1)))
    def test_dashboard_figures_match_before_optimization(self, now):
        self.populated_loan()
        self.populated_loan(due_date=date(2026, 2, 1), status="overdue")
        self.populated_loan(status="repaid")
        optimized = views._build_loans_dashboard_context()
        with (
            patch.object(views, "remaining_balances_from_related", lambda loan: loan.calculate_remaining_balances()),
            patch.object(views, "_dashboard_due_balance", Loan.calculate_total_amount_due_balance),
        ):
            original = views._build_loans_dashboard_context()
        self.assertEqual(optimized, original)

    def test_main_dashboard_cache_is_separate_from_summary(self):
        self.addCleanup(cache.clear)
        cache.clear()
        cache.set(views.CACHE_KEY, {"summary_only": True})
        request = RequestFactory().get("/dashboard/lms/")
        request.user = self.user
        with (
            patch.object(views, "_build_loans_dashboard_context", return_value={"total_loans": {}}) as build,
            patch.object(views, "render") as render,
        ):
            views.loans_dashboard(request)
            views.loans_dashboard(request)
        build.assert_called_once()
        self.assertEqual(render.call_args.args[2], {"total_loans": {}})
        self.assertEqual(cache.get(views.CACHE_KEY), {"summary_only": True})

    def test_lms_page_renders_on_cold_and_warm_cache(self):
        self.addCleanup(cache.clear)
        cache.clear()
        self.populated_loan()
        for _ in range(2):
            response = self.client.get("/dashboard/lms/")
            self.assertEqual(response.status_code, 200)
            self.assertTemplateUsed(response, "main/loans_dashboard.html")
            self.assertEqual(response.context["disbursed_loans"], 1)
