from django.urls import path

from . import views

urlpatterns = [
    # Child Sponsorship operations
    path("child-sponsorship/create/", views.child_sponsorship, name="child_sponsorship"),
    path(
        "child-sponsorship/report/",
        views.child_sponsorship_report,
        name="child_sponsorship_report",
    ),
    path(
        "sponsor-to-child/report/",
        views.sponsor_to_child_rpt,
        name="sponsor_to_child_rpt",
    ),
    path(
        "child-sponsorship/delete/<int:pk>/",
        views.delete_child_sponsorship,
        name="delete_child_sponsorship",
    ),
    path(
        "child-sponsorship/terminate/<int:sponsorship_id>/",
        views.terminate_child_sponsorship,
        name="terminate_child_sponsorship",
    ),
    path(
        "child-sponsorship/<int:sponsorship_id>/edit/",
        views.edit_child_sponsorship,
        name="edit_child_sponsorship",
    ),
    # Staff Sponsorship operations
    path(
        "staff-sponsorship/create/",
        views.staff_sponsorship_create,
        name="staff_sponsorship_create",
    ),
    path(
        "staff-sponsorship/report/",
        views.staff_sponsorship_report,
        name="staff_sponsorship_report",
    ),
    path(
        "sponsor-to-staff/report/",
        views.sponsor_to_staff_rpt,
        name="sponsor_to_staff_rpt",
    ),
    path(
        "staff-sponsorship/delete/<int:pk>/",
        views.delete_staff_sponsorship,
        name="delete_staff_sponsorship",
    ),
    path(
        "staff-sponsorship/terminate/<int:sponsorship_id>/",
        views.terminate_staff_sponsorship,
        name="terminate_staff_sponsorship",
    ),
    path(
        "staff-sponsorship/<int:sponsorship_id>/edit/",
        views.edit_staff_sponsorship,
        name="edit_staff_sponsorship",
    ),
    # MoMo Payment operations
    path("initiate/", views.initiate_payment, name="initiate_payment"),
    path("waiting/", views.waiting, name="waiting"),
    path("callback/", views.momo_callback, name="momo_callback"),
    path(
        "transaction-status/<str:ref_id>/",
        views.get_transaction_status,
        name="transaction_status",
    ),
    path("thank-you/", views.thank_you, name="thank_you"),
    path("transactions/", views.momo_transaction_list, name="momo_transaction_list"),
    path(
        "transactions/delete/<int:pk>/",
        views.delete_momo_transaction,
        name="delete_momo_transaction",
    ),
]
