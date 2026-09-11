from django.db import migrations

KEEP_SLUGS = {"pandas-introduction", "data-transformation"}
KEEP_TRACK = "data-analytics-with-python"


def slim_catalog(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Track = apps.get_model("exercises", "Track")

	Exercise.objects.exclude(slug__in=KEEP_SLUGS).delete()
	Track.objects.exclude(slug=KEEP_TRACK).delete()

	track = Track.objects.filter(slug=KEEP_TRACK).first()
	if track:
		track.is_placeholder = False
		track.published = True
		track.save(update_fields=["is_placeholder", "published"])

	for slug, order in (("pandas-introduction", 10), ("data-transformation", 20)):
		exercise = Exercise.objects.filter(slug=slug).first()
		if not exercise:
			continue
		exercise.order = order
		exercise.published = True
		exercise.is_placeholder = False
		if track:
			exercise.track = track
		exercise.save(update_fields=["order", "published", "is_placeholder", "track"])


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):

	dependencies = [
		("exercises", "0018_activate_ab_testing"),
	]

	operations = [
		migrations.RunPython(slim_catalog, noop_reverse),
	]
