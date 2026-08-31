from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path, re_path

from api.docs import documentation_home, schema_view
from apps.users.forms import LoginForm
from apps.users.views import (
    ChangePasswordView,
    CustomLoginView,
    LoginVerificationView,
    ResetPasswordView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.users.urls")),
    path(
        "login/",
        CustomLoginView.as_view(
            redirect_authenticated_user=True,
            template_name="accounts/login.html",
            authentication_form=LoginForm,
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(template_name="accounts/logout.html"),
        name="logout",
    ),
    path(
        "login/verify/",
        LoginVerificationView.as_view(),
        name="login_verify",
    ),
    path("password-reset/", ResetPasswordView.as_view(), name="password_reset"),
    path(
        "password-reset-confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(template_name="accounts/password_reset_confirm.html"),
        name="password_reset_confirm",
    ),
    path(
        "password-reset-complete/",
        auth_views.PasswordResetCompleteView.as_view(template_name="accounts/password_reset_complete.html"),
        name="password_reset_complete",
    ),
    path("password-change/", ChangePasswordView.as_view(), name="password_change"),
    re_path(r"^oauth/", include("social_django.urls", namespace="social")),
    path("api/v1/", include("api.v1.urls")),
    path("api/docs/", documentation_home, name="api-docs-home"),
    path("api/docs/swagger/", schema_view.with_ui("swagger", cache_timeout=0), name="api-docs-swagger"),
    path("api/docs/redoc/", schema_view.with_ui("redoc", cache_timeout=0), name="api-docs-redoc"),
    path("api/docs/schema.json", schema_view.without_ui(cache_timeout=0), name="api-docs-schema"),
    path("child/", include("apps.child.urls")),
    path("sponsor/", include("apps.sponsor.urls")),
    path("sponsorship/", include("apps.sponsorship.urls")),
    path("staff/", include("apps.staff.urls")),
    path("finance/", include("apps.finance.urls")),
    # Savings is isolated as its own app. It is also mounted under /finance/
    # to preserve existing staff/client portal links on Railway deployments.
    path("finance/", include("apps.savings.urls")),
    path("savings/", include("apps.savings.urls")),
    path("client/", include("apps.client.urls")),
    path("reports/", include("apps.reports.urls")),
    path("dashboard/", include("apps.dashboard.urls")),
    path("loans/", include("apps.loans.urls")),
    # Inventory ulrs
    path("customers/", include("apps.inventory.customers.urls")),
    path("products/", include("apps.inventory.products.urls")),
    path("sales/", include("apps.inventory.sales.urls")),
    path("supplier/", include("apps.inventory.supplier.urls")),
]

if settings.DEBUG:
    urlpatterns += [
        path("__reload__/", include("django_browser_reload.urls")),
    ]
    if getattr(settings, "ENABLE_DEBUG_TOOLBAR", False):
        urlpatterns += [path("__debug__/", include("debug_toolbar.urls"))]

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
