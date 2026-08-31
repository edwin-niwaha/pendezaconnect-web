from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("users", "0007_usernotification")]

    operations = [
        migrations.AddField(
            model_name="usernotification",
            name="deduplication_key",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddConstraint(
            model_name="usernotification",
            constraint=models.UniqueConstraint(
                condition=~models.Q(deduplication_key=""),
                fields=("user", "deduplication_key"),
                name="unique_user_notification_deduplication_key",
            ),
        ),
    ]
