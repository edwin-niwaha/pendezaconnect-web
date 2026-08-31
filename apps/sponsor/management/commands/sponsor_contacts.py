from django.core.management.base import BaseCommand

from ...models import Sponsor


class Command(BaseCommand):
    help = "Update all sponsors' contact numbers to include a prefix + sign"

    def handle(self, *args, **kwargs):
        sponsors = Sponsor.objects.all()
        updated_count = 0

        for sponsor in sponsors:
            updated = False

            if sponsor.business_telephone and not str(sponsor.business_telephone).startswith("+"):
                sponsor.business_telephone = "+" + str(sponsor.business_telephone)
                updated = True

            if sponsor.mobile_telephone and not str(sponsor.mobile_telephone).startswith("+"):
                sponsor.mobile_telephone = "+" + str(sponsor.mobile_telephone)
                updated = True

            if updated:
                sponsor.save()
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} sponsors' contacts."))
