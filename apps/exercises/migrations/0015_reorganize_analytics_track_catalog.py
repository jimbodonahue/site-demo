from django.db import migrations

PLACEHOLDER_INTRO = """This exercise is coming soon.

It will appear here as part of the **Data Analytics with Python** track. Check back later for an interactive notebook.
"""

CATALOG = [
	{
		"slug": "pandas-introduction",
		"title": "Pandas Introduction",
		"order": 10,
		"is_placeholder": False,
		"create": False,
	},
	{
		"slug": "data-transformation",
		"title": "Data Transformation",
		"order": 20,
		"is_placeholder": True,
		"create": True,
		"summary": "Reshape, map, and prepare tabular data for analysis.",
	},
	{
		"slug": "data-cleaning-messy-dataset",
		"title": "Data Cleaning: Messy Dataset",
		"order": 30,
		"is_placeholder": True,
		"create": True,
		"summary": "Repair dirty values, inconsistent labels, duplicates, and type issues.",
	},
	{
		"slug": "clean-messy-dataset",
		"title": "Data Cleaning: Missing Values",
		"order": 40,
		"is_placeholder": False,
		"create": False,
	},
	{
		"slug": "descriptive-statistics",
		"title": "Descriptive Statistics",
		"order": 50,
		"is_placeholder": True,
		"create": True,
		"summary": "Summarize distributions and communicate what the numbers say.",
	},
	{
		"slug": "ab-testing-conditional-probability",
		"title": "A/B Testing and Conditional Probability",
		"order": 60,
		"is_placeholder": True,
		"create": True,
		"summary": "Compare groups and reason about conditional outcomes.",
	},
]

REMOVED_SLUG = "fill-missing-values-generated-data"


def reorganize_catalog(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Track = apps.get_model("exercises", "Track")

	track = Track.objects.filter(slug="data-analytics-with-python").first()
	if not track:
		track = Track.objects.create(
			title="Data Analytics with Python",
			slug="data-analytics-with-python",
			summary="Build practical data analysis skills with pandas and Python.",
			order=10,
			published=True,
			is_placeholder=False,
		)

	# Remove the redundant parquet-based Fill Missing Values exercise.
	Exercise.objects.filter(slug=REMOVED_SLUG).delete()

	for item in CATALOG:
		defaults = {
			"title": item["title"],
			"order": item["order"],
			"published": True,
			"is_placeholder": item["is_placeholder"],
			"track": track,
		}
		if item["create"]:
			defaults["intro_markdown"] = PLACEHOLDER_INTRO
			exercise, created = Exercise.objects.update_or_create(
				slug=item["slug"],
				defaults=defaults,
			)
			if created or exercise.is_placeholder:
				# Keep placeholder rows minimal.
				exercise.intro_markdown = PLACEHOLDER_INTRO
				exercise.starter_code = ""
				exercise.allowed_imports = ["numpy", "pandas", "matplotlib.pyplot"]
				exercise.data_definition = {}
				exercise.evaluation_rules = {}
				exercise.graphic_markup = ""
				exercise.soft_skill_prompt = ""
				exercise.save()
		else:
			Exercise.objects.filter(slug=item["slug"]).update(**defaults)


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):
	dependencies = [
		("exercises", "0014_exercise_placeholder_and_catalog"),
	]

	operations = [
		migrations.RunPython(reorganize_catalog, noop_reverse),
	]
