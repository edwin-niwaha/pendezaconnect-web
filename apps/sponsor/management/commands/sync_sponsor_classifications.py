from django.core.management.base import BaseCommand
from django.db import transaction

from apps.sponsor.models import Sponsor, sponsorship_type_flags


class Command(BaseCommand):
    help = "Backfill sponsor classification flags from legacy relationships and payments."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Calculate changes without saving them.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of sponsors to stream from the database at a time.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        updated = 0

        queryset = Sponsor.objects.prefetch_related(
            "sponsored_children",
            "sponsored_staff",
            "child_payments",
            "staff_payments",
            "payments__program",
        ).order_by("id")

        for sponsor in queryset.iterator(chunk_size=batch_size):
            original = {
                "is_child_sponsor": sponsor.is_child_sponsor,
                "is_staff_sponsor": sponsor.is_staff_sponsor,
                "is_family_supporter": sponsor.is_family_supporter,
                "is_general_donor": sponsor.is_general_donor,
                "is_one_time_donor": sponsor.is_one_time_donor,
            }
            flags = self.classify(sponsor)
            changed_fields = [field for field, value in flags.items() if getattr(sponsor, field) != value]

            if not changed_fields:
                continue

            for field in changed_fields:
                setattr(sponsor, field, flags[field])

            updated += 1
            self.stdout.write(
                f"{'Would update' if dry_run else 'Updated'} sponsor {sponsor.id}: " f"{original} -> {flags}"
            )
            if not dry_run:
                sponsor.save(update_fields=[*changed_fields, "updated_at"])

        if dry_run:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING(f"Dry run complete. Sponsors changed: {updated}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Sponsor classifications synced: {updated}"))

    def classify(self, sponsor):
        flags = {
            "is_child_sponsor": False,
            "is_staff_sponsor": False,
            "is_family_supporter": False,
            "is_general_donor": False,
            "is_one_time_donor": False,
        }
        flags.update(sponsorship_type_flags(sponsor.sponsorship_type))

        flags["is_child_sponsor"] = flags["is_child_sponsor"] or any(
            sponsorship.is_active for sponsorship in sponsor.sponsored_children.all()
        )
        flags["is_staff_sponsor"] = flags["is_staff_sponsor"] or any(
            sponsorship.is_active for sponsorship in sponsor.sponsored_staff.all()
        )
        flags["is_child_sponsor"] = flags["is_child_sponsor"] or sponsor.child_payments.exists()
        flags["is_staff_sponsor"] = flags["is_staff_sponsor"] or sponsor.staff_payments.exists()

        for payment in sponsor.payments.all():
            code = payment.program.code
            if code in ("child_support", "child_co_support"):
                flags["is_child_sponsor"] = True
            elif code == "staff_support":
                flags["is_staff_sponsor"] = True
            elif code in ("family_support", "family_co_support"):
                flags["is_family_supporter"] = True
            elif code == "general_support":
                flags["is_general_donor"] = True
            elif code == "one_time_donation":
                flags["is_one_time_donor"] = True

        return flags
