from api.v1.serializers.auth_serializers import (
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    UserProfileSerializer,
    UserProfileUpdateSerializer,
)
from api.v1.serializers.child_serializers import ChildPhotoUploadSerializer, ChildSerializer
from api.v1.serializers.client_serializers import (
    ClientSerializer,
    SavingsAccountSerializer,
    SavingsRequestSerializer,
    SavingsTransactionSerializer,
)
from api.v1.serializers.device_installation_serializers import DeviceInstallationSerializer
from api.v1.serializers.google_auth_serializers import GoogleLoginSerializer
from api.v1.serializers.loan_serializers import (
    LoanActionSerializer,
    LoanApplicationDocumentSerializer,
    LoanApplicationSerializer,
    LoanSerializer,
)
from api.v1.serializers.payment_serializers import (
    ChildPaymentSerializer,
    PaymentSerializer,
    StaffPaymentSerializer,
)
from api.v1.serializers.sponsor_serializers import SponsorSerializer
from api.v1.serializers.staff_serializers import StaffSerializer

__all__ = [
    "AvatarUploadSerializer",
    "ChangePasswordSerializer",
    "ChildPaymentSerializer",
    "ChildPhotoUploadSerializer",
    "ChildSerializer",
    "ClientSerializer",
    "DeviceInstallationSerializer",
    "DeviceInstallationSerializer",
    "GoogleLoginSerializer",
    "LoanSerializer",
    "LoanActionSerializer",
    "LoanApplicationDocumentSerializer",
    "LoanApplicationSerializer",
    "PaymentSerializer",
    "SavingsAccountSerializer",
    "SavingsRequestSerializer",
    "SavingsTransactionSerializer",
    "SponsorSerializer",
    "StaffPaymentSerializer",
    "StaffSerializer",
    "UserProfileSerializer",
    "UserProfileUpdateSerializer",
]
