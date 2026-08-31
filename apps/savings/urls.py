from django.urls import path

from . import views

urlpatterns = [
    path("", views.financial_services_dashboard, name="financial_services_dashboard"),
    path(
        "dashboard/",
        views.financial_services_dashboard,
        name="financial_services_dashboard",
    ),
    path("savings/", views.savings_account_list, name="savings_account_list"),
    path("savings/create/", views.savings_account_create, name="savings_account_create"),
    path(
        "savings/<int:account_id>/",
        views.savings_account_detail,
        name="savings_account_detail",
    ),
    path(
        "savings/<int:account_id>/transactions/create/",
        views.savings_transaction_create,
        name="savings_transaction_create_for_account",
    ),
    path(
        "savings/transactions/create/",
        views.savings_transaction_create,
        name="savings_transaction_create",
    ),
    path(
        "savings/transactions/<int:transaction_id>/approve/",
        views.savings_transaction_approve,
        name="savings_transaction_approve",
    ),
    path(
        "savings/transactions/<int:transaction_id>/reject/",
        views.savings_transaction_reject,
        name="savings_transaction_reject",
    ),
    path(
        "client/savings/",
        views.client_savings_dashboard,
        name="client_savings_dashboard",
    ),
    path(
        "client/savings/statement/",
        views.client_savings_statement,
        name="client_savings_statement",
    ),
    path(
        "client/savings/request/",
        views.client_savings_request,
        name="client_savings_request",
    ),
    path(
        "client/savings/deposit/mobile-money/",
        views.client_savings_deposit_payment,
        name="client_savings_deposit_payment",
    ),
    path(
        "client/savings/deposit/waiting/",
        views.client_savings_deposit_waiting,
        name="client_savings_deposit_waiting",
    ),
    path(
        "client/savings/deposit/status/<str:reference>/",
        views.client_savings_deposit_status,
        name="client_savings_deposit_status",
    ),
    path(
        "client/savings/deposit/",
        views.client_savings_deposit_request,
        name="client_savings_deposit_request",
    ),
    path(
        "client/savings/withdraw/",
        views.client_savings_withdrawal_request,
        name="client_savings_withdrawal_request",
    ),
]
