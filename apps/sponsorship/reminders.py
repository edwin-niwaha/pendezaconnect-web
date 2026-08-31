from django.db.models import Q
from django.utils import timezone

from apps.finance.models import Payment
from apps.sponsorship.models import ChildSponsorship, StaffSponsorship
from apps.users.notification_recipients import NotificationRecipients
from apps.users.notification_service import notification_service


class SponsorshipReminderService:
    def send_monthly_due(self, reminder_date=None):
        reminder_date = reminder_date or timezone.localdate()
        paid_sponsor_ids = Payment.objects.filter(
            payment_date__year=reminder_date.year,
            payment_date__month=reminder_date.month,
        ).values_list("sponsor_id", flat=True)
        active_filter = Q(is_active=True) & (Q(end_date__isnull=True) | Q(end_date__gte=reminder_date))
        sponsor_ids = set(ChildSponsorship.objects.filter(active_filter).values_list("sponsor_id", flat=True))
        sponsor_ids.update(StaffSponsorship.objects.filter(active_filter).values_list("sponsor_id", flat=True))
        sponsor_ids.difference_update(paid_sponsor_ids)

        notifications = 0
        period = reminder_date.strftime("%Y-%m")
        for sponsor_id in sponsor_ids:
            notifications += len(
                notification_service.notify(
                    NotificationRecipients.sponsors(sponsor_id),
                    "sponsorship_due",
                    sponsor_id,
                    deduplication_key=f"sponsorship-due:{sponsor_id}:{period}",
                )
            )
        return notifications


sponsorship_reminder_service = SponsorshipReminderService()
