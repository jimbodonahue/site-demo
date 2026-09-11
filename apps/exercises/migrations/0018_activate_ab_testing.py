from django.db import migrations


INTRO_MARKDOWN = """Practice A/B decisions and conditional probability with seeded experiment data.

On most difficulties the platform already splits outcomes into `group_a` and `group_b`. Read the request with `print(task['prompt'])`, inspect `df`, then record your decision variables.

### What to do
1. Choose a difficulty in the left panel. Change it anytime for a fresh challenge.
2. Inspect `df` and any pre-split groups.
3. Complete the statistical or Bayes task from the prompt.
4. Run the notebook and confirm the check passes.

Helpers: `welch_ttest(group_a, group_b)` returns `t_statistic`, `df`, and two-sided `p_value`.
"""

SOFT_SKILL_PROMPT = (
	"Generate a null hypothesis for the comparison in this task, and connect it to what you "
	"actually tested. In 2–4 sentences, state H0 clearly and explain what rejecting (or not "
	"rejecting) it would mean for the product or business decision."
)

EVALUATION_RULES = {
	"required_variables": ["df", "task"],
	"assertions": [
		"ab_testing_passes(task, different=different, relevant=relevant, answer=answer, p_value=p_value)",
	],
	"success_message": "Nice work. Your A/B or Bayes conclusion matches the expected decision.",
	"failure_message": (
		"Your decision is not correct yet. Re-check the prompt: use a t-test decision "
		"(`different` / `relevant` + `p_value`) or a Bayes posterior in `answer`."
	),
}


def activate_ab_testing(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	exercise = Exercise.objects.filter(slug="ab-testing-conditional-probability").first()
	if not exercise:
		return

	exercise.title = "A/B Testing and Conditional Probability"
	exercise.is_placeholder = False
	exercise.published = True
	exercise.order = 60
	exercise.intro_markdown = INTRO_MARKDOWN
	exercise.soft_skill_prompt = SOFT_SKILL_PROMPT
	exercise.starter_code = ""
	exercise.allowed_imports = ["numpy", "pandas", "matplotlib.pyplot"]
	exercise.data_definition = {
		"dataframe_source": "ab_testing",
		"initial_data": {
			"seed": 42,
			"difficulty": "easy",
			"selected_feature": "easy",
			"dataframe_source": "ab_testing",
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
		"Use notebook output to inspect group summaries and your test results "
		"(<code>welch_ttest(group_a, group_b)</code>)."
		"</p>"
	)
	exercise.save()


def deactivate_ab_testing(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Exercise.objects.filter(slug="ab-testing-conditional-probability").update(
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
		("exercises", "0017_activate_messy_dataset"),
	]

	operations = [
		migrations.RunPython(activate_ab_testing, deactivate_ab_testing),
	]
