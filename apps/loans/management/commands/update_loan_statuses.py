# apps/loans/management/commands/update_loan_statuses.py

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.loans.models import Loan


class Command(BaseCommand):
    help = "Update loan statuses (disbursed/approved → overdue/repaid) based on due dates and payments"

    def handle(self, *args, **options):
        # Only fetch loans that could possibly change
        queryset = Loan.objects.filter(status__in=["disbursed", "approved"])

        total = queryset.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS("No loans need status update."))
            return

        self.stdout.write(f"Checking {total} active loans for status changes...")

        updated = 0
        batch_size = 1000
        loans_to_save = []

        # Use iterator() + chunk_size to avoid memory issues with 10k+ loans
        for loan in queryset.iterator(chunk_size=batch_size):
            old_status = loan.status
            loan.update_status()  # This method only modifies loan.status in memory

            if loan.status != old_status:
                loans_to_save.append(loan)
                updated += 1

                # Save in batches inside atomic transactions
                if len(loans_to_save) >= batch_size:
                    self._save_batch(loans_to_save)
                    loans_to_save.clear()

        # Save remaining loans
        if loans_to_save:
            self._save_batch(loans_to_save)

        self.stdout.write(self.style.SUCCESS(f"Done! Checked {total} loans → {updated} updated."))

    @staticmethod
    @transaction.atomic
    def _save_batch(loans):
        """
        Save only the status field for a batch of loans.
        Each loan may have a different final status (overdue or repaid).
        """
        Loan.objects.bulk_update(loans, ["status"], batch_size=1000)
