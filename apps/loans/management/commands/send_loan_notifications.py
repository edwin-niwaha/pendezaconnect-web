import logging
from datetime import timedelta
from typing import Dict, List

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.html import strip_tags

from apps.loans.models import Loan
from apps.loans.services.loan_reminder_service import LoanReminderService
from apps.loans.tasks import is_blocked_borrower_email
from core.memory import log_process_memory

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Send loan reminders on configured weekdays.

    Defaults to Monday and Thursday so borrower emails go out twice a week.
    The command can still be run manually with --force for urgent follow-up.
    """

    help = "Send automated loan reminders and a management summary."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate sending emails without actually sending them.",
        )
        parser.add_argument(
            "--pre-due-days",
            type=int,
            default=7,
            help="Number of days before due date to include upcoming reminders.",
        )
        parser.add_argument(
            "--cooldown-days",
            type=int,
            default=3,
            help="Minimum days before the same loan can receive another reminder.",
        )
        parser.add_argument(
            "--notification-weekdays",
            default="0,3",
            help="Comma-separated weekdays for sending reminders. Monday=0, Thursday=3.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Send even when today is outside configured notification weekdays.",
        )

    def handle(self, *args, **options):
        self.dry_run = options["dry_run"]
        self.pre_due_days = options["pre_due_days"]
        self.cooldown_days = options["cooldown_days"]
        self.notification_weekdays = self.parse_weekdays(options["notification_weekdays"])

        today = timezone.localdate()
        weekday = today.weekday()

        if self.dry_run:
            self.stdout.write(self.style.WARNING("Running in DRY-RUN mode"))

        if weekday not in self.notification_weekdays and not options["force"]:
            scheduled = ", ".join(str(day) for day in sorted(self.notification_weekdays))
            self.stdout.write(
                self.style.WARNING(
                    f"Skipping loan reminders. Today is weekday {weekday}; "
                    f"configured send days are {scheduled}. Use --force to override."
                )
            )
            return

        logger.info("Loan reminder job started.")
        log_process_memory("send_loan_notifications.start")

        loans = (
            Loan.objects.filter(status__in=Loan.ACTIVE_STATUSES)
            .select_related("borrower")
            .prefetch_related("repayments", "penalties")
        )

        summary: Dict[str, List[Dict]] = {
            "pre_due": [],
            "due_today": [],
            "overdue": [],
        }
        total_processed = 0
        total_sent = 0

        for loan in loans.iterator(chunk_size=200):
            try:
                total_processed += 1

                service = LoanReminderService(
                    loan=loan,
                    today=today,
                    pre_due_days=self.pre_due_days,
                )
                info = service.get_info()
                if not info:
                    continue

                if loan.last_reminder_sent and info["category"] != "overdue":
                    delta = timezone.now() - loan.last_reminder_sent
                    if delta < timedelta(days=self.cooldown_days):
                        logger.debug("Loan #%s skipped; reminder cooldown active.", loan.id)
                        continue

                sent = self.send_email(loan, info, today)
                if sent:
                    total_sent += 1
                    summary[info["category"]].append(self.summary_item(loan, info))
                    loan.last_reminder_sent = timezone.now()
                    loan.save(update_fields=["last_reminder_sent"])

            except Exception:
                logger.exception("Loan #%s failed during reminder processing.", loan.id)

        self.send_summary(today, summary)
        logger.info("Loan reminder job completed.")
        log_process_memory("send_loan_notifications.finish")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nProcessed: {total_processed} loans\n"
                f"Emails sent: {total_sent}\n"
                f"Upcoming: {len(summary['pre_due'])}\n"
                f"Due today: {len(summary['due_today'])}\n"
                f"Overdue: {len(summary['overdue'])}"
            )
        )

    def parse_weekdays(self, raw_value):
        try:
            weekdays = {int(value.strip()) for value in raw_value.split(",") if value.strip() != ""}
        except ValueError as exc:
            raise CommandError("--notification-weekdays must contain only integers.") from exc

        invalid = [day for day in weekdays if day < 0 or day > 6]
        if invalid:
            raise CommandError("--notification-weekdays values must be between 0 and 6.")
        if not weekdays:
            raise CommandError("--notification-weekdays must include at least one day.")

        return weekdays

    def send_email(self, loan: Loan, info: Dict, today) -> bool:
        borrower = loan.borrower

        if not borrower.email:
            logger.warning("Loan #%s skipped; borrower has no email.", loan.id)
            return False

        if is_blocked_borrower_email(borrower.email):
            logger.info(
                "Loan #%s reminder skipped for blocked borrower email: %s",
                loan.id,
                borrower.email,
            )
            return False

        template_by_category = {
            "pre_due": "emails/loan_pre_due.html",
            "due_today": "emails/loan_due_today.html",
            "overdue": "emails/loan_overdue.html",
        }
        subject_by_category = {
            "pre_due": f"Upcoming loan payment - Loan #{loan.id}",
            "due_today": f"Loan payment due today - Loan #{loan.id}",
            "overdue": f"Overdue loan payment - Loan #{loan.id}",
        }

        category = info["category"]
        context = {
            "title": info["notice_title"],
            "loan": loan,
            "borrower": borrower,
            "today_str": today.strftime("%d %b %Y"),
            "detail_url": "https://sponsorwithpendeza.org/loans/due-overdue-report/",
            **info,
        }

        html_content = render_to_string(template_by_category[category], context)
        text_content = strip_tags(html_content)

        if self.dry_run:
            logger.info("[DRY RUN] Would send %s email to %s", category, borrower.email)
            return True

        email = EmailMultiAlternatives(
            subject=subject_by_category[category],
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[borrower.email],
        )
        email.attach_alternative(html_content, "text/html")

        try:
            email.send(fail_silently=False)
            logger.info("%s reminder sent to %s", category, borrower.email)
            return True
        except Exception:
            logger.exception("Email failed for Loan #%s", loan.id)
            return False

    @staticmethod
    def summary_item(loan: Loan, info: Dict) -> Dict:
        return {
            "loan": {"id": loan.id},
            "loan_id": loan.id,
            "borrower_name": loan.borrower.full_name,
            "category": info["category"],
            "notice_title": info["notice_title"],
            "action_label": info["action_label"],
            "action_amount": info["action_amount"],
            "payment_due_date": info["payment_due_date"],
            "total_outstanding": info["total_outstanding"],
            "days_until": info.get("days_until"),
            "days_overdue": info.get("days_overdue"),
        }

    def send_summary(self, today, summary):
        recipients = [
            email
            for email in [
                getattr(settings, "BOO_EMAIL", None),
                getattr(settings, "HOF_EMAIL", None),
            ]
            if email
        ]

        if not recipients:
            logger.warning("No summary recipients configured. Summary skipped.")
            return

        context = {
            "title": "Loan reminders summary",
            "today_str": today.strftime("%d %b %Y"),
            "pre_due": summary["pre_due"],
            "due_today": summary["due_today"],
            "overdue": summary["overdue"],
            "total_sent": sum(len(items) for items in summary.values()),
            "report_url": "https://sponsorwithpendeza.org/loans/due-overdue-report/",
        }

        html = render_to_string("emails/loan_summary.html", context)
        text = strip_tags(html)

        if self.dry_run:
            logger.info("[DRY RUN] Would send summary to %s", recipients)
            return

        email = EmailMultiAlternatives(
            f"Loan reminders summary - {today.strftime('%d %b %Y')}",
            text,
            settings.DEFAULT_FROM_EMAIL,
            recipients,
        )
        email.attach_alternative(html, "text/html")

        try:
            email.send(fail_silently=False)
            logger.info("Summary email sent successfully to %s.", recipients)
        except Exception:
            logger.exception("Summary email failed.")
