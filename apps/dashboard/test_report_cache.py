from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.child.models import Child
from apps.inventory.sales.models import Sale
from apps.loans import test_aging_report
from apps.loans.services import reporting
from apps.loans.services.reporting import aging_report_rows, repayment_rows
from apps.loans.views import _loan_report_rows
from apps.reports.views import _build_reports_dashboard
from core.report_cache import cached_chart, invalidate_report_cache, report_snapshot

from . import views


class ReportCacheTests(TestCase):
    loan = test_aging_report.AgingReportTests.loan
    payment = test_aging_report.AgingReportTests.payment

    def setUp(self):
        test_aging_report.AgingReportTests.setUp(self)
        cache.clear()
        self.addCleanup(cache.clear)
        self.filters = {"end_date": date(2026, 3, 1)}

    def test_report_rows_reuse_snapshot_across_pagination_export_and_mutations(self):
        self.loan()
        first = aging_report_rows(self.filters)
        self.assertEqual(len(first), 1)
        first[0]["client"] = "Changed by presentation layer"
        first[0]["disbursement_date"] = "01/01/2026"
        with self.assertNumQueries(0):
            again = aging_report_rows({**self.filters, "per_page": 100, "export": "csv", "arrears_over": "30"})
        self.assertEqual(again[0]["client"], self.borrower.full_name)
        self.assertIsInstance(again[0]["disbursement_date"], date)
        self.assertEqual(aging_report_rows({**self.filters, "q": "no matching client"}), [])
        self.assertEqual(aging_report_rows({"end_date": date(2025, 1, 1)}), [])

    def test_portfolio_and_collection_snapshots_do_not_requery(self):
        loan = self.loan()
        self.payment(loan, date(2026, 2, 1), principal="20")
        portfolio = _loan_report_rows({})
        collections = repayment_rows({})
        with self.assertNumQueries(0):
            self.assertEqual(_loan_report_rows({"per_page": 25}), portfolio)
            self.assertEqual(repayment_rows({"export": "csv"}), collections)
        self.assertEqual(_loan_report_rows({}, statuses=["closed"]), [])

    def test_saved_source_invalidates_only_its_domain_after_commit(self):
        self.loan()
        original = aging_report_rows(self.filters)
        sponsorship_builder = Mock(return_value={"total": 5})
        report_snapshot("sponsorship", "test", {}, sponsorship_builder)
        with self.captureOnCommitCallbacks(execute=True):
            self.borrower.full_name = "Renamed Client"
            self.borrower.save(update_fields=["full_name"])
            self.assertEqual(aging_report_rows(self.filters), original)
        self.assertEqual(aging_report_rows(self.filters)[0]["client"], "Renamed Client")
        report_snapshot("sponsorship", "test", {}, sponsorship_builder)
        sponsorship_builder.assert_called_once()

    def test_deletion_invalidates_inventory_snapshot(self):
        sale = Sale.objects.create(trans_date=date(2026, 3, 1), grand_total=100)
        self.assertEqual(views._monthly_sales(2026)[2], 100)
        with self.captureOnCommitCallbacks(execute=True):
            sale.delete()
        self.assertEqual(views._monthly_sales(2026)[2], 0)

    def test_dashboard_data_builders_use_no_queries_on_cache_hit(self):
        self.loan()
        builders = [views._build_sponsorship_dashboard, views._build_inventory_dashboard, _build_reports_dashboard]
        for build in builders:
            expected = build()
            with self.assertNumQueries(0):
                self.assertEqual(build(), expected)

    def test_monthly_sales_uses_one_query_and_cache(self):
        Sale.objects.bulk_create([
            Sale(trans_date=date(2026, 1, 1), grand_total=10),
            Sale(trans_date=date(2026, 1, 15), grand_total=20),
            Sale(trans_date=date(2026, 3, 1), grand_total=40),
            Sale(trans_date=date(2025, 1, 1), grand_total=999),
        ])
        with self.assertNumQueries(1):
            months = views._monthly_sales(2026)
        self.assertEqual(months, [30, 0, 40] + [0] * 9)
        with self.assertNumQueries(0):
            self.assertEqual(views._monthly_sales(2026), months)

    def test_chart_hits_cache_but_still_requires_login(self):
        request = RequestFactory().get("/dashboard/birthdays_by_month/")
        request.user = self.user
        Child.objects.create(full_name="Birthday Child", date_of_birth=date(2000, 2, 1))
        expected = views.birthdays_by_month(request)
        with self.assertNumQueries(0):
            self.assertEqual(views.birthdays_by_month(request).content, expected.content)
        request.user = AnonymousUser()
        self.assertEqual(views.birthdays_by_month(request).status_code, 302)

    def test_failed_chart_response_is_not_cached(self):
        build = Mock(side_effect=[JsonResponse({}, status=500), JsonResponse({"ok": True})])
        build.__name__ = "failing_chart"
        view = cached_chart("loans")(build)
        request = RequestFactory().get("/")
        self.assertEqual(view(request).status_code, 500)
        self.assertEqual(view(request).status_code, 200)
        self.assertEqual(build.call_count, 2)

    def test_expiry_and_day_rollover_rebuild_snapshot(self):
        build = Mock(return_value={"total": 1})
        with patch("django.core.cache.backends.locmem.time.time", return_value=1000):
            report_snapshot("loans", "expiry", {}, build)
        with patch("django.core.cache.backends.locmem.time.time", return_value=1301):
            report_snapshot("loans", "expiry", {}, build)
        self.assertEqual(build.call_count, 2)
        with patch("core.report_cache.timezone.localdate", return_value=date(2030, 1, 1)):
            report_snapshot("loans", "expiry", {}, build)
        self.assertEqual(build.call_count, 3)

    def test_cache_unavailable_falls_back_to_builder(self):
        with (
            patch("core.report_cache.cache.get", side_effect=ConnectionError),
            self.assertLogs("core.report_cache", level="WARNING"),
        ):
            self.assertEqual(report_snapshot("loans", "failure", {}, lambda: [1]), [1])

    def test_aging_risk_and_csv_share_rows_without_corrupting_dates(self):
        self.loan()
        with patch.object(reporting, "filtered_loans", wraps=reporting.filtered_loans) as query:
            for name, querystring in (
                ("loan_aging_report", {}),
                ("portfolio_at_risk_report", {}),
                ("loan_aging_report", {"export": "csv"}),
            ):
                response = self.client.get(
                    reverse("loans:" + name), {"end_date": "2026-03-01", **querystring}
                )
                self.assertEqual(response.status_code, 200)
        query.assert_called_once()

    def test_rolled_back_change_does_not_invalidate_snapshot(self):
        self.loan()
        original = aging_report_rows(self.filters)
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.borrower.full_name = "Rolled back"
                self.borrower.save(update_fields=["full_name"])
                transaction.set_rollback(True)
        with self.assertNumQueries(0):
            self.assertEqual(aging_report_rows(self.filters), original)

    @override_settings(REPORT_CACHE_TTL=0)
    def test_cache_can_be_disabled(self):
        build = Mock(return_value=[])
        report_snapshot("loans", "disabled", {}, build)
        report_snapshot("loans", "disabled", {}, build)
        self.assertEqual(build.call_count, 2)

    def test_bulk_import_can_explicitly_invalidate(self):
        self.assertEqual(aging_report_rows(self.filters), [])
        self.loan()
        invalidate_report_cache("loans")
        self.assertEqual(len(aging_report_rows(self.filters)), 1)
