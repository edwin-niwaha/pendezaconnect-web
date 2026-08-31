from datetime import timedelta

from django.utils import timezone

from apps.loans.models import Loan
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import notification_service


class LoanReminderService:
    def send_due_soon(self, reminder_date=None):
        reminder_date = reminder_date or timezone.localdate()
        due_date = reminder_date + timedelta(days=1)
        loans = Loan.objects.filter(
            due_date=due_date,
            status__in=("approved", "disbursed", "overdue"),
        ).only("id", "borrower_id")
        notifications = 0
        for loan in loans.iterator():
            notifications += len(
                notification_service.notify(
                    NotificationRecipients.clients(loan.borrower_id),
                    "loan_payment_due",
                    loan.id,
                    deduplication_key=f"loan-payment-due:{loan.id}:{due_date}",
                )
            )
        return notifications


loan_reminder_service = LoanReminderService()
