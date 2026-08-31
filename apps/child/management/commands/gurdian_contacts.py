from django.core.management.base import BaseCommand

from ...models import Child


class Command(BaseCommand):
    help = "Update all guardian contact numbers to include a prefix + sign"

    def handle(self, *args, **kwargs):
        children = Child.objects.all()
        updated_count = 0

        for child in children:
            if child.guardian_contact and not str(child.guardian_contact).startswith("+"):
                child.guardian_contact = "+" + str(child.guardian_contact)
                child.save()
                updated_count += 1

        self.stdout.write(self.style.SUCCESS(f"Successfully updated {updated_count} guardian contacts."))
