import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("forum", "0003_topic_sections"),
    ]

    operations = [
        migrations.CreateModel(
            name="ForumConductReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("message", models.TextField()),
                ("previous_page", models.CharField(blank=True, default="", max_length=500)),
                ("reported_nickname", models.CharField(blank=True, default="", max_length=150)),
                ("want_reply", models.BooleanField(default=False)),
                ("reply_email", models.EmailField(blank=True, default="", max_length=254)),
                ("user_agent", models.CharField(blank=True, default="", max_length=300)),
                ("email_sent", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "reporter",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="forum_conduct_reports",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Forum conduct report",
                "verbose_name_plural": "Forum conduct reports",
                "ordering": ["-created_at"],
            },
        ),
    ]
