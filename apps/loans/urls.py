from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    # Client self-service URLs
    path("self-service/apply/", views.client_loan_apply, name="client_loan_apply"),
    path(
        "self-service/applications/",
        views.client_loan_applications,
        name="client_loan_applications",
    ),
    path(
        "self-service/applications/<int:loan_id>/",
        views.client_loan_application_detail,
        name="client_loan_application_detail",
    ),
    path(
        "self-service/applications/<int:loan_id>/documents/<int:document_id>/open/",
        views.client_loan_application_document_open,
        name="client_loan_application_document_open",
    ),
    # Loan application URLs
    path("apply/", views.loan_apply, name="apply_for_loan"),
    path("applications/", views.loan_applications_view, name="loan_applications"),
    path(
        "applications/all",
        views.loan_applications_all_view,
        name="loan_applications_all",
    ),
    path("approved/", views.approved_loans_view, name="approved_loans"),
    path("loan/update/<int:loan_id>/", views.update_loan, name="update_loan"),
    path("disbursed/", views.disbursed_loans_view, name="disbursed_loans"),
    path("rejected_loans/", views.rejected_loans_view, name="rejected_loans"),
    path("disburse_all_loans/", views.disburse_all_loans, name="disburse_all_loans"),
    path(
        "loan/<int:loan_id>/repayment-schedule/",
        views.repayment_schedule,
        name="repayment_schedule",
    ),
    # Loan management URLs
    path("<int:loan_id>/approve/", views.approve_loan, name="approve_loan"),
    path("approve-all-loans/", views.approve_all_loans, name="approve_all_loans"),
    path("reject/<int:loan_id>/", views.reject_loan, name="reject_loan"),
    path("disburse/", views.disburse_loan, name="disburse_loan"),
    path("application/delete/<int:loan_id>/", views.delete_loan, name="delete_loan"),
    # Loan repayment
    path(
        "repay/",
        views.loan_repayment_create_view,
        name="loan_repayment_create",
    ),
    path(
        "<int:loan_id>/documents/upload/",
        views.upload_loan_application_document,
        name="upload_loan_application_document",
    ),
    path(
        "<int:loan_id>/documents/<int:document_id>/open/",
        views.loan_application_document_open,
        name="loan_application_document_open",
    ),
    path(
        "<int:loan_id>/documents/<int:document_id>/download/",
        views.loan_application_document_download,
        name="loan_application_document_download",
    ),
    path("<int:loan_id>/", views.loan_detail_view, name="loan_detail"),
    path(
        "repayment/delete/<int:repayment_id>/",
        views.delete_repayment,
        name="delete_repayment",
    ),
    path("penalty/create/", views.loan_penalty_create_view, name="loan_penalty_create"),
    path("loan-aging-report/", views.loan_aging_report, name="loan_aging_report"),
    path("loan-arrears-report/", views.loan_arrears_report, name="loan-arrears-report"),
    path("loan-portfolio/", views.loan_portfolio_report, name="loan_portfolio_report"),
    path(
        "reports/disbursements/",
        views.loan_disbursement_report,
        name="loan_disbursement_report",
    ),
    path(
        "reports/collections/",
        views.loan_collection_report,
        name="loan_collection_report",
    ),
    path(
        "reports/outstanding-balances/",
        views.outstanding_loan_balances_report,
        name="outstanding_balances_report",
    ),
    path(
        "reports/defaulted/",
        views.defaulted_loans_report,
        name="defaulted_loans_report",
    ),
    path("reports/closed/", views.closed_loans_report, name="closed_loans_report"),
    path(
        "reports/officer-performance/",
        views.loan_officer_performance_report,
        name="loan_officer_performance_report",
    ),
    path(
        "reports/product-performance/",
        views.loan_product_performance_report,
        name="loan_product_performance_report",
    ),
    path("portfolio-at-risk/", views.portfolio_at_risk, name="portfolio_at_risk_report"),
    path("loans/non-performing/", views.non_performing_loans, name="non_performing_loans"),
    path("import/", views.import_loan_data, name="import_loan_data"),
    # Chart of accounts URLs
    path("accounts/add/", views.add_chart_of_account_view, name="add_chart_of_account"),
    path("accounts/", views.chart_of_accounts_list_view, name="chart_of_accounts_list"),
    path(
        "accounts/update/<str:account_id>/",
        views.chart_of_account_update_view,
        name="chart_of_account_update",
    ),
    path(
        "accounts/delete/<str:account_id>/",
        views.chart_of_account_delete_view,
        name="chart_of_account_delete",
    ),
    path("import-accounts/", views.import_coa_data, name="import_coa_data"),
    path("ledger_report/", views.ledger_report_view, name="ledger_report"),
    path(
        "ledger_report/<int:account_id>/",
        views.ledger_report_view,
        name="ledger_report_with_id",
    ),
    path("loans-dash/", views.loan_reports_dashboard, name="loan_reports_dashboard"),
    path("statement/", views.client_loan_statement, name="loan_statement"),
    path(
        "due-overdue-report/",
        views.loan_due_overdue_report,
        name="due_overdue_report",
    ),
    path(
        "penalties/manage/",
        views.loan_penalty_management,
        name="loan_penalty_management",
    ),
]
