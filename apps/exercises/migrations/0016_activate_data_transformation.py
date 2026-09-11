from django.db import migrations


INTRO_MARKDOWN = """Practice transforming a messy retail product table into analysis-ready pieces.

The working table is available as `df`. Read the request with `print(task['prompt'])`, inspect the columns (including messy fields like `size_raw` and `in_stock`), then produce the dataframes the prompt asks for.

### What to do
1. Choose a difficulty in the left panel. Change it anytime for a fresh challenge.
2. Inspect `df` and the task prompt.
3. Build `df0`, `df1`, and `df2` to match the request.
4. Run the notebook and confirm the check passes.

Tip: start with `df.head()` and `df[['size_raw', 'satisfaction', 'in_stock']].value_counts()` to see what needs cleaning or encoding.
"""

SOFT_SKILL_PROMPT = (
	"Consider how these encodings may affect a regression downstream. "
	"For example, if a satisfaction score is treated as a numeric predictor, "
	"are the steps on a Likert scale really equal? "
	"In 2–4 sentences, explain one risk of the encoding choices you made "
	"(or would make) and how you might communicate that to a teammate."
)

EVALUATION_RULES = {
	"required_variables": ["df", "task", "df0", "df1", "df2"],
	"assertions": [
		"data_transformation_passes(task, df0=df0, df1=df1, df2=df2)",
	],
	"success_message": "Nice work. Your transformed dataframes match the task.",
	"failure_message": (
		"df0/df1/df2 do not match the expected transforms yet. "
		"Re-read the prompt and check column names, encodings, filters, and row order."
	),
}


def activate_data_transformation(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	exercise = Exercise.objects.filter(slug="data-transformation").first()
	if not exercise:
		return

	exercise.title = "Data Transformation"
	exercise.is_placeholder = False
	exercise.published = True
	exercise.order = 20
	exercise.intro_markdown = INTRO_MARKDOWN
	exercise.soft_skill_prompt = SOFT_SKILL_PROMPT
	exercise.starter_code = ""
	exercise.allowed_imports = ["numpy", "pandas", "matplotlib.pyplot"]
	exercise.data_definition = {
		"dataframe_source": "data_transformation",
		"initial_data": {
			"seed": 42,
			"difficulty": "easy",
			"selected_feature": "easy",
			"n_rows": 90,
			"dataframe_source": "data_transformation",
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
		"Use the notebook output to inspect your transformed frames "
		"(<code>df0.head()</code>, <code>df1.head()</code>, <code>df2.head()</code>)."
		"</p>"
	)
	exercise.save()


def deactivate_data_transformation(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Exercise.objects.filter(slug="data-transformation").update(
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
		("exercises", "0015_reorganize_analytics_track_catalog"),
	]

	operations = [
		migrations.RunPython(activate_data_transformation, deactivate_data_transformation),
	]
