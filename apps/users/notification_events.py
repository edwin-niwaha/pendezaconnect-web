from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationTemplate:
    title: str
    body: str


EVENT_TEMPLATES = {
    "loan_submitted": NotificationTemplate(
        "Loan application received",
        "Your loan application was submitted successfully and is awaiting review.",
    ),
    "loan_updated": NotificationTemplate(
        "Loan status updated",
        "The status of your loan has changed. Open Loans to review it.",
    ),
    "loan_disbursed": NotificationTemplate(
        "Loan disbursed",
        "Your loan has been disbursed. Open Loans to review the details.",
    ),
    "loan_status_changed": NotificationTemplate(
        "Client loan status changed",
        "A client loan has moved to a new status. Open Loans to review it.",
    ),
    "loan_payment_due": NotificationTemplate(
        "Loan payment due soon",
        "A loan repayment is due tomorrow. Open Loans to review it.",
    ),
    "payment_updated": NotificationTemplate(
        "Payment update",
        "Your payment status was updated.",
    ),
    "savings_updated": NotificationTemplate(
        "Savings update",
        "Your savings account was updated.",
    ),
    "client_savings_changed": NotificationTemplate(
        "Client savings changed",
        "A client's savings record has changed. Open Savings to review it.",
    ),
    "account_security_changed": NotificationTemplate(
        "Security update",
        "Your account security information changed.",
    ),
    "savings_request_submitted": NotificationTemplate(
        "Savings request received",
        "Your savings request was submitted and is awaiting review.",
    ),
    "sponsorship_due": NotificationTemplate(
        "Sponsorship reminder",
        "Your sponsorship contribution is due. Open Payments to review it.",
    ),
    "loan_approval_required": NotificationTemplate(
        "Loan approval required",
        "A loan has reached your approval stage. Open Loans to review it.",
    ),
    "loan_disbursement_required": NotificationTemplate(
        "Loan ready for disbursement",
        "A loan has completed approval and is ready for disbursement.",
    ),
    "inventory_low_stock": NotificationTemplate(
        "Low stock",
        "An inventory item has reached its reorder level. Open Stock Alerts to review it.",
    ),
    "inventory_out_of_stock": NotificationTemplate(
        "Out of stock",
        "An inventory item is out of stock. Open Stock Alerts to review it.",
    ),
}


def get_notification_template(event):
    try:
        return EVENT_TEMPLATES[event]
    except KeyError as exc:
        raise ValueError(f"Unsupported notification event: {event}") from exc
