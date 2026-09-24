"""Restore analytics exercise placeholders and the ML track for the lite catalog.

Live exercises remain pandas-introduction and data-transformation only.
"""

from django.db import migrations

PLACEHOLDER_INTRO = """This exercise is coming soon.

It will appear here as part of the **Data Analytics with Python** track. Check back later for an interactive notebook.
"""

PLACEHOLDER_EXERCISES = [
	{
		"slug": "data-cleaning-messy-dataset",
		"title": "Data Cleaning: Messy Dataset",
		"order": 30,
		"summary": "Repair dirty values, inconsistent labels, duplicates, and type issues.",
	},
	{
		"slug": "clean-messy-dataset",
		"title": "Data Cleaning: Missing Values",
		"order": 40,
		"summary": "Detect, diagnose, and handle missing values in real tabular data.",
	},
	{
		"slug": "descriptive-statistics",
		"title": "Descriptive Statistics",
		"order": 50,
		"summary": "Summarize distributions and communicate what the numbers say.",
	},
	{
		"slug": "ab-testing-conditional-probability",
		"title": "A/B Testing and Conditional Probability",
		"order": 60,
		"summary": "Compare groups and reason about conditional outcomes.",
	},
]

LIVE_SLUGS = ("pandas-introduction", "data-transformation")


def restore_placeholders(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Track = apps.get_model("exercises", "Track")

	analytics, _ = Track.objects.update_or_create(
		slug="data-analytics-with-python",
		defaults={
			"title": "Data Analytics with Python",
			"summary": (
				"Build practical data analysis skills with pandas and Python: "
				"explore tabular data, handle missing values, and clean real-world datasets."
			),
			"order": 10,
			"published": True,
			"is_placeholder": False,
		},
	)
	Track.objects.update_or_create(
		slug="machine-learning-and-ai",
		defaults={
			"title": "Machine Learning and AI",
			"summary": (
				"Coming soon: supervised learning, model evaluation, and applied AI workflows. "
				"Exercises for this track are on the way."
			),
			"order": 20,
			"published": True,
			"is_placeholder": True,
		},
	)

	for order, slug in enumerate(LIVE_SLUGS, start=1):
		Exercise.objects.filter(slug=slug).update(
			track=analytics,
			order=order * 10,
			published=True,
			is_placeholder=False,
		)

	for item in PLACEHOLDER_EXERCISES:
		exercise, _ = Exercise.objects.update_or_create(
			slug=item["slug"],
			defaults={
				"title": item["title"],
				"order": item["order"],
				"published": True,
				"is_placeholder": True,
				"track": analytics,
				"intro_markdown": PLACEHOLDER_INTRO,
				"starter_code": "",
				"allowed_imports": ["numpy", "pandas", "matplotlib.pyplot"],
				"data_definition": {},
				"evaluation_rules": {},
				"graphic_markup": "",
				"soft_skill_prompt": "",
			},
		)
		# Ensure placeholder rows stay minimal even if the slug already existed.
		exercise.is_placeholder = True
		exercise.published = True
		exercise.track = analytics
		exercise.order = item["order"]
		exercise.title = item["title"]
		exercise.intro_markdown = PLACEHOLDER_INTRO
		exercise.starter_code = ""
		exercise.allowed_imports = ["numpy", "pandas", "matplotlib.pyplot"]
		exercise.data_definition = {}
		exercise.evaluation_rules = {}
		exercise.graphic_markup = ""
		exercise.soft_skill_prompt = ""
		exercise.save()


def remove_placeholders(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Track = apps.get_model("exercises", "Track")
	slugs = [item["slug"] for item in PLACEHOLDER_EXERCISES]
	Exercise.objects.filter(slug__in=slugs).delete()
	Track.objects.filter(slug="machine-learning-and-ai").delete()


class Migration(migrations.Migration):

	dependencies = [
		("exercises", "0020_typed_evaluation_rules"),
	]

	operations = [
		migrations.RunPython(restore_placeholders, remove_placeholders),
	]
