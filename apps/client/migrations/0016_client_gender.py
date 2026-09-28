from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("client", "0015_sync_mobile_client_photos")]

    operations = [
        migrations.AddField(
            model_name="client",
            name="gender",
            field=models.CharField(
                max_length=6, choices=[("Male", "Male"), ("Female", "Female")],
                blank=True, default="", verbose_name="Gender",
            ),
        ),
    ]
