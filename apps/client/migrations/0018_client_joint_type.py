from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("client", "0017_client_profile_fields")]
    operations = [
        migrations.AlterField(
            model_name="client",
            name="client_type",
            field=models.CharField(
                max_length=20,
                default="individual",
                verbose_name="Client type",
                choices=[
                    ("individual", "Individual"),
                    ("group", "Group"),
                    ("joint", "Joint"),
                    ("organization", "Organization"),
                ],
            ),
        ),
    ]
