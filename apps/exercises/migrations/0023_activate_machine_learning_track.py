"""Activate the Machine Learning and AI track with six interactive exercises."""

from django.db import migrations


COMMON_META = {
	"version": 2,
	"second_seed_recheck": {"enabled": True, "seed_offset": 10007},
	"soft_skill": {"required_for_full_completion": True, "min_chars": 40, "min_words": 8},
}

ALLOWED_IMPORTS = [
	"numpy",
	"pandas",
	"matplotlib.pyplot",
	"sklearn",
	"xgboost",
]

FEATURE_CHOICES = [
	{"label": "Easy", "value": "easy"},
	{"label": "Medium", "value": "medium"},
	{"label": "Hard", "value": "hard"},
]

MESSAGE_DEFAULTS = {
	"ml-data-preparation": (
		"Nice work. Your data-preparation answers match the expected split diagnostics.",
		"Not quite yet. Re-check encodings, seeds/folds, and the values stored in `answer`.",
	),
	"ml-regression-strategies": (
		"Nice work. Your regression results match the expected model comparison.",
		"Not quite yet. Re-check the model family, parameters, and reported score.",
	),
	"ml-intro-classification": (
		"Nice work. Your classification results match the expected comparison.",
		"Not quite yet. Re-check the chosen classifier, hyperparameters, and metric.",
	),
	"ml-advanced-classification": (
		"Nice work. Your advanced classification answers match the expected metrics.",
		"Not quite yet. Re-check imbalance handling, thresholds, or multi-class CV scores.",
	),
	"ml-ensemble-methods": (
		"Nice work. Your ensemble results match the expected comparison or search.",
		"Not quite yet. Re-check the forest/XGBoost settings and reported score.",
	),
	"ml-unsupervised-learning": (
		"Nice work. Your clustering answers match the expected cluster summaries.",
		"Not quite yet. Re-check scaling, K, and the cluster size/mean summaries.",
	),
}


def _rules(passer: str, success: str, failure: str) -> dict:
	return {
		**COMMON_META,
		"success_message": success,
		"failure_message": failure,
		"graders": [
			{
				"id": "required_df",
				"type": "required_variable",
				"variable": "df",
				"section": "core",
				"soft": True,
				"next_action": "Keep working from `df` and any provided train/test arrays.",
			},
			{
				"id": "required_task",
				"type": "required_variable",
				"variable": "task",
				"section": "core",
				"soft": True,
				"next_action": "Reload the exercise if `task` is missing.",
			},
			{
				"id": "required_answer",
				"type": "required_variable",
				"variable": "answer",
				"section": "core",
				"soft": True,
				"next_action": "Store results in the `answer` dict.",
			},
			{
				"id": "ml_core",
				"type": "assertion",
				"expression": passer,
				"section": "core",
				"soft": False,
				"next_action": "Re-read `task['prompt']` and recompute `answer` from `df` / the split arrays.",
				"failure_message": "Result does not match the task yet.",
			},
		],
	}


def _data_definition(source: str) -> dict:
	return {
		"dataframe_source": source,
		"initial_data": {
			"seed": 42,
			"difficulty": "easy",
			"selected_feature": "easy",
			"dataframe_source": source,
		},
		"feature_choices": FEATURE_CHOICES,
		"difficulty_choices": FEATURE_CHOICES,
	}


def activate_ml_track(apps, schema_editor):
	# Use runtime models/helpers so content files on disk are applied.
	from apps.exercises.content import load_json, sync_exercise_from_content
	from apps.exercises.models import Exercise, Track

	catalog = load_json("ml_catalog.json", default={})
	exercises = catalog.get("exercises") or []
	allowed = list(catalog.get("allowed_imports") or ALLOWED_IMPORTS)

	track, _ = Track.objects.update_or_create(
		slug="machine-learning-and-ai",
		defaults={
			"title": "Machine Learning and AI",
			"summary": (
				"Prepare data, train supervised models, handle class imbalance, "
				"tune ensembles, and explore unsupervised structure — with short, "
				"sandbox-friendly runs."
			),
			"order": 20,
			"published": True,
			"is_placeholder": False,
		},
	)

	for item in exercises:
		slug = item["slug"]
		source = item["source"]
		passer = item["passer"]
		success, failure = MESSAGE_DEFAULTS.get(
			slug,
			("Nice work.", "Not quite yet. Re-read the prompt and recompute `answer`."),
		)
		defaults = {
			"title": item["title"],
			"order": item["order"],
			"published": True,
			"is_placeholder": False,
			"track": track,
			"starter_code": "",
			"allowed_imports": allowed,
			"data_definition": _data_definition(source),
			"evaluation_rules": _rules(passer, success, failure),
			"graphic_markup": "",
			"soft_skill_prompt": "",
			"intro_markdown": (
				f"Practice {item['title'].lower()} in the interactive notebook.\n\n"
				"Read `task['prompt']`, work from `df` (and any pre-split arrays), "
				"then fill `answer`."
			),
		}
		exercise, _created = Exercise.objects.update_or_create(slug=slug, defaults=defaults)
		fields = sync_exercise_from_content(exercise)
		if fields:
			exercise.save(update_fields=[*fields, "updated_at"])


def deactivate_ml_track(apps, schema_editor):
	from apps.exercises.models import Exercise, Track

	slugs = [
		"ml-data-preparation",
		"ml-regression-strategies",
		"ml-intro-classification",
		"ml-advanced-classification",
		"ml-ensemble-methods",
		"ml-unsupervised-learning",
	]
	Exercise.objects.filter(slug__in=slugs).update(
		is_placeholder=True,
		published=True,
		intro_markdown=(
			"This exercise is coming soon.\n\n"
			"It will appear here as part of the **Machine Learning and AI** track. "
			"Check back later for an interactive notebook.\n"
		),
		soft_skill_prompt="",
		data_definition={},
		evaluation_rules={},
		track=None,
	)
	Track.objects.filter(slug="machine-learning-and-ai").update(
		is_placeholder=True,
		summary=(
			"Coming soon: supervised learning, model evaluation, and applied AI workflows. "
			"Exercises for this track are on the way."
		),
	)


class Migration(migrations.Migration):
	dependencies = [
		("exercises", "0022_sync_exercise_content_files"),
	]

	operations = [
		migrations.RunPython(activate_ml_track, deactivate_ml_track),
	]
