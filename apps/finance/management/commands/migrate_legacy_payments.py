from django.core.management.base import BaseCommand
from django.db import transaction

from apps.finance.models import (
    ChildPayments,
    DonorPayment,
    Payment,
    StaffPayments,
    SupportProgram,
)
from apps.sponsor.models import Sponsor, SponsorshipType


class Command(BaseCommand):
    help = "Safely copy old payment records into the new unified Payment table"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the copy logic inside a transaction and roll it back.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of legacy rows to stream from the database at a time.",
        )

    def get_program(self, code):
        return SupportProgram.objects.get(code=code)

    def resolve_child_program(self, sponsor):
        if sponsor.sponsorship_type == SponsorshipType.CHILD_CO_SUPPORT:
            return self.get_program(SupportProgram.CHILD_CO_SUPPORT)

        return self.get_program(SupportProgram.CHILD_SUPPORT)

    def get_or_create_sponsor_from_donor(self, donor):
        if donor.email:
            sponsor = Sponsor.objects.filter(email__iexact=donor.email).first()
            if sponsor:
                return sponsor, False

        first_name = donor.full_name or "Unknown"
        last_name = ""

        parts = first_name.split(" ", 1)
        if len(parts) == 2:
            first_name, last_name = parts

        return (
            Sponsor.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=donor.email or "",
                gender="Male",
                sponsorship_type="",
                expected_amt=0,
                is_one_time_donor=True,
            ),
            True,
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]

        staff_support = self.get_program(SupportProgram.STAFF_SUPPORT)
        one_time = self.get_program(SupportProgram.ONE_TIME_DONATION)

        child_created = 0
        staff_created = 0
        donor_created = 0
        sponsor_created = 0

        for old in (
            ChildPayments.objects.filter(is_valid=True)
            .select_related("sponsor", "child")
            .iterator(chunk_size=batch_size)
        ):
            program = self.resolve_child_program(old.sponsor)

            _, created = Payment.objects.get_or_create(
                source_model="ChildPayments",
                source_id=old.id,
                defaults={
                    "sponsor": old.sponsor,
                    "program": program,
                    "child": old.child,
                    "amount": old.amount,
                    "payment_date": old.payment_date,
                    "notes": f"Legacy child payment: {old.month} {old.payment_year}",
                },
            )

            if created:
                child_created += 1
            if not old.sponsor.is_child_sponsor:
                old.sponsor.is_child_sponsor = True
                old.sponsor.save(update_fields=["is_child_sponsor", "updated_at"])

        for old in (
            StaffPayments.objects.filter(is_valid=True)
            .select_related("sponsor", "staff")
            .iterator(chunk_size=batch_size)
        ):
            _, created = Payment.objects.get_or_create(
                source_model="StaffPayments",
                source_id=old.id,
                defaults={
                    "sponsor": old.sponsor,
                    "program": staff_support,
                    "staff": old.staff,
                    "amount": old.amount,
                    "payment_date": old.payment_date,
                    "notes": f"Legacy staff payment: {old.month} {old.payment_year}",
                },
            )

            if created:
                staff_created += 1
            if not old.sponsor.is_staff_sponsor:
                old.sponsor.is_staff_sponsor = True
                old.sponsor.save(update_fields=["is_staff_sponsor", "updated_at"])

        for old in DonorPayment.objects.select_related("donor").iterator(chunk_size=batch_size):
            sponsor, created_sponsor = self.get_or_create_sponsor_from_donor(old.donor)
            if created_sponsor:
                sponsor_created += 1

            _, created = Payment.objects.get_or_create(
                source_model="DonorPayment",
                source_id=old.id,
                defaults={
                    "sponsor": sponsor,
                    "program": one_time,
                    "amount": old.amount,
                    "payment_date": old.payment_date,
                    "notes": "Legacy donor payment migrated as one-time donation",
                },
            )

            if created:
                donor_created += 1

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING("Dry run complete; no rows were saved."))
        else:
            self.stdout.write(self.style.SUCCESS("Legacy payment migration complete."))
        self.stdout.write(f"Child payments copied: {child_created}")
        self.stdout.write(f"Staff payments copied: {staff_created}")
        self.stdout.write(f"Donor payments copied: {donor_created}")
        self.stdout.write(f"One-time donor sponsors created: {sponsor_created}")
