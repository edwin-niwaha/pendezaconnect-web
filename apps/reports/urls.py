from django.urls import path

from . import views

urlpatterns = [
    # Dashboard
    path("reports-dashboard/", views.reports_dash, name="reports_dash"),
    # Children
    path("children/master-list", views.children_master_list, name="children_master_list"),
    path("children/list", views.all_children, name="all_children"),
    path("sponsored-children/", views.sponsored_children, name="sponsored_children"),
    path(
        "non-sponsored-children/",
        views.un_sponsored_children,
        name="un_sponsored_children",
    ),
    path("departed-children/", views.departed_children, name="departed_children"),
    # Sponsors
    path("departed-sponsors/", views.departed_sponsors, name="departed_sponsors"),
    # Payments
    path("payments-child/", views.sponsor_payments_child, name="sponsor_payments_child"),
    path("payments-staff/", views.sponsor_payments_staff, name="sponsor_payments_staff"),
    # Staff
    path("sponsored-staff/", views.sponsored_staff, name="sponsored_staff"),
    path("non-sponsored-staff/", views.non_sponsored_staff, name="non_sponsored_staff"),
    path("departed-staff/", views.departed_staff, name="departed_staff"),
]
