from django.db import migrations


INTRO_MARKDOWN = """Practice cleaning a deliberately messy sales table until it is analysis-ready.

The dirty table is available as `df`. Read the request with `print(task['prompt'])`. On some difficulties you will also get a lookup table as `df_extra` that must be joined in.

### What to do
1. Choose a difficulty in the left panel. Change it anytime for a fresh challenge.
2. Inspect `df` (and `df_extra` when present).
3. Clean and reshape the data so `df` matches the tidy schema in the prompt.
4. Run the notebook and confirm the check passes.

Tip: the first row may contain the real column names. Start with `df.head(10)` before assuming the headers are correct.
"""

SOFT_SKILL_PROMPT = (
	"Contemplate how one could create a data pipeline that takes care of these issues "
	"before they get to the data analyst. In 2–4 sentences, describe where such checks "
	"might live (ingestion, scheduled jobs, warehouse tests) and one benefit of catching "
	"problems earlier."
)

EVALUATION_RULES = {
	"required_variables": ["df", "task"],
	"assertions": [
		"messy_dataset_passes(df, task)",
	],
	"success_message": "Nice work. Your cleaned dataframe matches the tidy sales table.",
	"failure_message": (
		"df is not clean yet. Restore headers, remove blank/duplicate rows, fix types and "
		"similar values, repair OCR-like typos when present, drop duplicate columns, and "
		"join df_extra if the prompt requires it."
	),
}


def activate_messy_dataset(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	exercise = Exercise.objects.filter(slug="data-cleaning-messy-dataset").first()
	if not exercise:
		return

	exercise.title = "Data Cleaning: Messy Dataset"
	exercise.is_placeholder = False
	exercise.published = True
	exercise.order = 30
	exercise.intro_markdown = INTRO_MARKDOWN
	exercise.soft_skill_prompt = SOFT_SKILL_PROMPT
	exercise.starter_code = ""
	exercise.allowed_imports = ["numpy", "pandas", "matplotlib.pyplot"]
	exercise.data_definition = {
		"dataframe_source": "messy_dataset",
		"initial_data": {
			"seed": 42,
			"difficulty": "easy",
			"selected_feature": "easy",
			"n_rows": 48,
			"dataframe_source": "messy_dataset",
		},
		"feature_choices": [
			{"label": "Easy", "value": "easy"},
			{"label": "Medium", "value": "medium"},
			{"label": "Hard", "value": "hard"},
		],
		"difficulty_choices": [
			{"label": "Easy", "value": "easy"},
			{"label": "Medium", "value": "medium"},
			{"label": "Hard", "value": "hard"},
		],
	}
	exercise.evaluation_rules = EVALUATION_RULES
	exercise.graphic_markup = (
		"<p class='text-sm text-slate-600 dark:text-slate-300'>"
		"Inspect your cleaned <code>df.head()</code> output in the notebook. "
		"The progress check compares your table to the expected tidy schema."
		"</p>"
	)
	exercise.save()


def deactivate_messy_dataset(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Exercise.objects.filter(slug="data-cleaning-messy-dataset").update(
		is_placeholder=True,
		intro_markdown=(
			"This exercise is coming soon.\n\n"
			"It will appear here as part of the **Data Analytics with Python** track. "
			"Check back later for an interactive notebook.\n"
		),
		soft_skill_prompt="",
		data_definition={},
		evaluation_rules={},
	)


class Migration(migrations.Migration):
	dependencies = [
		("exercises", "0016_activate_data_transformation"),
	]

	operations = [
		migrations.RunPython(activate_messy_dataset, deactivate_messy_dataset),
	]
