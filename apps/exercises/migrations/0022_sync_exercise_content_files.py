"""Sync published exercise copy from content files into the database."""

from django.db import migrations


def sync_from_content(apps, schema_editor):
	# Import runtime helpers (not historical models) so we read the files on disk.
	from apps.exercises.content import sync_exercise_from_content
	from apps.exercises.models import Exercise

	for exercise in Exercise.objects.all():
		fields = sync_exercise_from_content(exercise)
		if fields:
			exercise.save(update_fields=[*fields, "updated_at"])


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):
	dependencies = [
		("exercises", "0021_data_transformation_join_hard"),
	]

	operations = [
		migrations.RunPython(sync_from_content, noop_reverse),
	]
