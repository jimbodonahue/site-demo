from django.db import migrations


INTRO_MARKDOWN = """Practice core descriptive statistics on a seeded survey table.

Read the request with `print(task['prompt'])`, inspect `df`, then fill the `answer` dict. On hard tasks, also create the requested plot and set `plotted = True`.

### What to do
1. Choose a difficulty in the left panel. Change it anytime for a fresh challenge.
2. Inspect `df` with `.head()`, `.describe()`, and (on medium/hard) group or correlation tools.
3. Compute the requested summaries and store them in `answer`.
4. Run the notebook and confirm the check passes.

Tips: use `df['col'].mean()`, `.median()`, `.mode()`, `.std()`, `.var()`, and `df.groupby(...)`.
"""

SOFT_SKILL_PROMPT = (
	"In 2–4 sentences, explain when you would prefer the median over the mean for a skewed "
	"measure in this dataset, and what a stakeholder might misunderstand if you only reported "
	"the mean."
)

EVALUATION_RULES = {
	"required_variables": ["df", "task"],
	"assertions": [
		"descriptive_statistics_passes(task, answer=answer, plotted=plotted)",
	],
	"success_message": "Nice work. Your descriptive statistics match the expected summaries.",
	"failure_message": (
		"Not quite yet. Re-read `task['prompt']`, check rounding, and on hard tasks remember "
		"to set `plotted = True` after your histogram or heatmap."
	),
}


def activate_descriptive_statistics(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	exercise = Exercise.objects.filter(slug="descriptive-statistics").first()
	if not exercise:
		return

	exercise.title = "Descriptive Statistics"
	exercise.is_placeholder = False
	exercise.published = True
	exercise.order = 50
	exercise.intro_markdown = INTRO_MARKDOWN
	exercise.soft_skill_prompt = SOFT_SKILL_PROMPT
	exercise.starter_code = ""
	exercise.allowed_imports = ["numpy", "pandas", "matplotlib.pyplot"]
	exercise.data_definition = {
		"dataframe_source": "descriptive_statistics",
		"initial_data": {
			"seed": 42,
			"difficulty": "easy",
			"selected_feature": "easy",
			"dataframe_source": "descriptive_statistics",
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
		"Use notebook output for summaries. On hard difficulty, draw a histogram or "
		"correlation heatmap with <code>matplotlib.pyplot</code>."
		"</p>"
	)
	exercise.save()


def deactivate_descriptive_statistics(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Exercise.objects.filter(slug="descriptive-statistics").update(
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
		("exercises", "0018_activate_ab_testing"),
	]

	operations = [
		migrations.RunPython(activate_descriptive_statistics, deactivate_descriptive_statistics),
	]
