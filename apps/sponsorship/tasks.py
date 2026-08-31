from celery import shared_task

from apps.sponsorship.reminders import sponsorship_reminder_service


@shared_task
def send_push_sponsorship_reminders():
    return sponsorship_reminder_service.send_monthly_due()
