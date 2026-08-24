import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("users", "0006_unique_user_email_ci"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event", models.CharField(max_length=50)),
                ("record_id", models.PositiveBigIntegerField(blank=True, null=True)),
                ("title", models.CharField(max_length=160)),
                ("body", models.TextField(max_length=500)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddIndex(model_name="usernotification", index=models.Index(fields=["user", "read_at"], name="users_notif_user_read_idx")),
        migrations.AddIndex(model_name="usernotification", index=models.Index(fields=["user", "created_at"], name="users_notif_user_date_idx")),
    ]
