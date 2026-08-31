from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from api.v1.views import (
    AuthViewSet,
    ChildViewSet,
    ClientViewSet,
    DashboardViewSet,
    DeviceInstallationViewSet,
    FeedbackViewSet,
    InventoryViewSet,
    LoanViewSet,
    PaymentViewSet,
    SponsorViewSet,
    StaffViewSet,
    UserNotificationViewSet,
)

router = DefaultRouter()
router.register("auth", AuthViewSet, basename="mobile-auth")
router.register("children", ChildViewSet, basename="mobile-children")
router.register("dashboard", DashboardViewSet, basename="mobile-dashboard")
router.register("sponsors", SponsorViewSet, basename="mobile-sponsors")
router.register("clients", ClientViewSet, basename="mobile-clients")
router.register("staff", StaffViewSet, basename="mobile-staff")
router.register("loans", LoanViewSet, basename="mobile-loans")
router.register("inventory", InventoryViewSet, basename="mobile-inventory")
router.register("payments", PaymentViewSet, basename="mobile-payments")
router.register("device-installations", DeviceInstallationViewSet, basename="mobile-device-installations")
router.register("notifications", UserNotificationViewSet, basename="mobile-notifications")
router.register("feedback", FeedbackViewSet, basename="mobile-feedback")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="mobile-token-refresh"),
]
