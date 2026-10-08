from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0010_exercise_progress_help_text"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="is_forum_suspended",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "When set, this user cannot post, like, or create forum topics. "
                    "Exercise access is unaffected."
                ),
                verbose_name="forum suspended",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="forum_suspended_until",
            field=models.DateTimeField(
                blank=True,
                help_text="Optional end time for a temporary forum suspension. Leave blank for indefinite.",
                null=True,
                verbose_name="forum suspended until",
            ),
        ),
        migrations.AddField(
            model_name="customuser",
            name="forum_suspension_note",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Internal moderator/admin note about why forum access was suspended.",
                verbose_name="forum suspension note",
            ),
        ),
    ]
