from api.v1.views.auth_views import AuthViewSet
from api.v1.views.child_viewsets import ChildViewSet
from api.v1.views.client_viewsets import ClientViewSet
from api.v1.views.dashboard_views import DashboardViewSet
from api.v1.views.device_installation_viewsets import DeviceInstallationViewSet
from api.v1.views.feedback_viewsets import FeedbackViewSet
from api.v1.views.inventory_viewsets import InventoryViewSet
from api.v1.views.loan_viewsets import LoanViewSet
from api.v1.views.notification_viewsets import UserNotificationViewSet
from api.v1.views.payment_viewsets import PaymentViewSet
from api.v1.views.sponsor_viewsets import SponsorViewSet
from api.v1.views.staff_viewsets import StaffViewSet

__all__ = [
    "AuthViewSet",
    "ChildViewSet",
    "ClientViewSet",
    "DashboardViewSet",
    "DeviceInstallationViewSet",
    "FeedbackViewSet",
    "LoanViewSet",
    "InventoryViewSet",
    "UserNotificationViewSet",
    "PaymentViewSet",
    "SponsorViewSet",
    "StaffViewSet",
]
