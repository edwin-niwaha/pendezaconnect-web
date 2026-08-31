import logging
from datetime import date, datetime

import pytz
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.loans.models import Loan
from core.memory import log_process_memory

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sends SMS notifications to borrowers for loans due today and overdue"

    def handle(self, *args, **kwargs):
        try:
            timezone.activate(pytz.timezone("Africa/Nairobi"))
        except pytz.exceptions.UnknownTimeZoneError:
            timezone.activate(pytz.UTC)

        today = timezone.now().date()
        disbursed_loans = Loan.objects.filter(status="disbursed").select_related("borrower")
        sent_sms = failed_sms = 0

        # Initialize Twilio client
        try:
            from twilio.rest import Client

            twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        except (AttributeError, ImportError):
            logger.error("Twilio is unavailable or credentials are not configured in settings")
            self.stdout.write(self.style.ERROR("Twilio unavailable or credentials not configured"))
            return

        log_process_memory("send_sms_notifications.start")

        # Process individual borrower SMS
        for loan in disbursed_loans.iterator(chunk_size=200):
            try:
                balances = loan.calculate_remaining_balances()
                total_balance = balances["principal_balance"] + balances["interest_balance"]
                if total_balance <= 0 or not loan.disbursement_date or loan.loan_period_months <= 0:
                    continue

                schedule = loan.generate_payment_schedule()
                borrower = loan.borrower
                borrower_name = borrower.get_full_name()
                borrower_phone = borrower.mobile_telephone

                # Validate phone number
                if not borrower_phone or not borrower_phone.is_valid() or borrower_phone.as_e164 == "+256999999999":
                    logger.warning(
                        f"Invalid, missing, or default mobile telephone for borrower {borrower_name} (Loan ID: {loan.id})"
                    )
                    failed_sms += 1
                    continue

                borrower_phone_str = borrower_phone.as_e164

                # Due loans (today)
                due_payments = [
                    p
                    for p in schedule
                    if isinstance(p["payment_due_date"], (date, datetime))
                    and (
                        p["payment_due_date"].date()
                        if isinstance(p["payment_due_date"], datetime)
                        else p["payment_due_date"]
                    )
                    == today
                ]
                if due_payments:
                    monthly_installment = sum(p["principal_payment"] + p["interest_payment"] for p in due_payments)
                    # Cap total_amount_due at total_balance
                    total_amount_due = min(monthly_installment, total_balance)

                    sms_body = (
                        f"Dear {borrower_name},\n"
                        f"Your Loan ID: {loan.id} payment of {total_amount_due:,.2f} is due today, {today.strftime('%Y-%m-%d')}.\n"
                        f"Total Outstanding Balance: {total_balance:,.2f}.\n"
                        f"Please pay promptly. - Pendeza Uganda"
                    )

                    try:
                        twilio_client.messages.create(
                            body=sms_body,
                            from_=settings.TWILIO_PHONE_NUMBER,
                            to=borrower_phone_str,
                        )
                        logger.info(f"Due loan SMS sent to {borrower_phone_str} for Loan {loan.id}")
                        sent_sms += 1
                    except Exception as e:
                        logger.error(f"Failed to send due loan SMS to {borrower_phone_str} for Loan {loan.id}: {e}")
                        failed_sms += 1
                        continue

                # Overdue loans
                overdue_payments = [
                    p
                    for p in schedule
                    if isinstance(p["payment_due_date"], (date, datetime))
                    and (
                        p["payment_due_date"].date()
                        if isinstance(p["payment_due_date"], datetime)
                        else p["payment_due_date"]
                    )
                    < today
                    and p["principal_payment"] + p["interest_payment"] > 0
                ]
                if loan.due_date and loan.due_date < today:
                    days_overdue = (today - loan.due_date).days
                    total_amount_due = total_balance  # Already capped

                    sms_body = (
                        f"Dear {borrower_name},\n"
                        f"Your Loan ID: {loan.id} is overdue by {days_overdue} days. Amount due: {total_amount_due:,.2f}.\n"
                        f"Total Outstanding Balance: {total_balance:,.2f}.\n"
                        f"Please pay immediately. - Pendeza Uganda"
                    )

                    try:
                        twilio_client.messages.create(
                            body=sms_body,
                            from_=settings.TWILIO_PHONE_NUMBER,
                            to=borrower_phone_str,
                        )
                        logger.info(f"Overdue loan SMS sent to {borrower_phone_str} for Loan {loan.id}")
                        sent_sms += 1
                    except Exception as e:
                        logger.error(f"Failed to send overdue loan SMS to {borrower_phone_str} for Loan {loan.id}: {e}")
                        failed_sms += 1
                        continue
                elif overdue_payments:
                    earliest_due_date = min(
                        (
                            p["payment_due_date"].date()
                            if isinstance(p["payment_due_date"], datetime)
                            else p["payment_due_date"]
                        )
                        for p in overdue_payments
                    )
                    if earliest_due_date < today:
                        days_overdue = (today - earliest_due_date).days
                        monthly_installment = sum(
                            p["principal_payment"] + p["interest_payment"] for p in overdue_payments
                        )
                        # Cap total_amount_due at total_balance
                        total_amount_due = min(monthly_installment, total_balance)

                        sms_body = (
                            f"Dear {borrower_name},\n"
                            f"Your Loan ID: {loan.id} is overdue by {days_overdue} days. Amount due: {total_amount_due:,.2f}.\n"
                            f"Total Outstanding Balance: {total_balance:,.2f}.\n"
                            f"Please pay immediately. - Pendeza Uganda"
                        )

                        try:
                            twilio_client.messages.create(
                                body=sms_body,
                                from_=settings.TWILIO_PHONE_NUMBER,
                                to=borrower_phone_str,
                            )
                            logger.info(f"Overdue loan SMS sent to {borrower_phone_str} for Loan {loan.id}")
                            sent_sms += 1
                        except Exception as e:
                            logger.error(
                                f"Failed to send overdue loan SMS to {borrower_phone_str} for Loan {loan.id}: {e}"
                            )
                            failed_sms += 1
                            continue

            except Exception as e:
                logger.error(f"Error processing Loan {loan.id}: {e}")
                failed_sms += 1
                continue

        if sent_sms == 0 and failed_sms == 0:
            logger.info("No loans due or overdue today")

        self.stdout.write(self.style.SUCCESS(f"SMS sent: {sent_sms}, Failed: {failed_sms}"))
        log_process_memory("send_sms_notifications.finish")
