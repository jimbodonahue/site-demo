from django.db import migrations, models


def forwards_seed_preferred_topics(apps, schema_editor):
	UserProfile = apps.get_model("authentication", "UserProfile")
	for profile in UserProfile.objects.all().iterator():
		existing = profile.preferred_topics if isinstance(profile.preferred_topics, list) else []
		if existing:
			continue
		legacy = (profile.data_field or "").strip().lower()
		if legacy:
			profile.preferred_topics = [legacy]
			profile.save(update_fields=["preferred_topics"])


def backwards_noop(apps, schema_editor):
	pass


class Migration(migrations.Migration):

	dependencies = [
		("authentication", "0006_userprofile_exercise_progress"),
	]

	operations = [
		migrations.AddField(
			model_name="userprofile",
			name="preferred_topics",
			field=models.JSONField(
				blank=True,
				default=list,
				help_text=(
					"Up to five preferred Data Zoo topics in ranked order. "
					"The first entry is the default used for new exercise attempts."
				),
			),
		),
		migrations.AlterField(
			model_name="userprofile",
			name="data_field",
			field=models.CharField(
				blank=True,
				default="",
				help_text="Primary (rank-1) preferred data science field for exercise datasets.",
				max_length=64,
			),
		),
		migrations.AlterField(
			model_name="userprofile",
			name="dataset_file",
			field=models.CharField(
				blank=True,
				default="",
				help_text="Optional preferred parquet dataset file for the primary topic.",
				max_length=200,
			),
		),
		migrations.RunPython(forwards_seed_preferred_topics, backwards_noop),
	]
