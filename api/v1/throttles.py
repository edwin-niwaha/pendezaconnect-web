from rest_framework.throttling import AnonRateThrottle


class LoginThrottle(AnonRateThrottle):
    scope = "login"


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class PaymentStartThrottle(AnonRateThrottle):
    scope = "payment_start"


class PaymentStatusThrottle(AnonRateThrottle):
    scope = "payment_status"
