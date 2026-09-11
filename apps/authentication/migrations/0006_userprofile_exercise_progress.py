from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0005_userprofile_data_field_userprofile_dataset_file_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="exercise_progress",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Per-exercise personal data state used to repeat saved attempts.",
            ),
        ),
    ]
