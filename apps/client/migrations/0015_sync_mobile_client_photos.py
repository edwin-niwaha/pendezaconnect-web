from django.db import migrations


def sync_mobile_client_photos(apps, schema_editor):
    Client = apps.get_model("client", "Client")
    ClientProfilePicture = apps.get_model("client", "ClientProfilePicture")

    for client in Client.objects.exclude(picture__isnull=True).exclude(picture=""):
        stored_picture = str(client.picture)
        photos = ClientProfilePicture.objects.filter(client_id=client.id)
        matching = photos.filter(picture=stored_picture).order_by("-uploaded_at", "-id").first()
        photos.filter(is_current=True).exclude(picture=stored_picture).update(is_current=False)
        if matching:
            if not matching.is_current:
                matching.is_current = True
                matching.save(update_fields=["is_current"])
        else:
            ClientProfilePicture.objects.create(
                client_id=client.id,
                picture=client.picture,
                is_current=True,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("client", "0014_sync_client_form_photos"),
    ]

    operations = [
        migrations.RunPython(sync_mobile_client_photos, migrations.RunPython.noop),
    ]
