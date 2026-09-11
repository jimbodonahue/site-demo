from django.db import migrations


PANDAS_INTRO_MARKDOWN = """Practice core pandas skills by turning a plain-language request into working code.

The patient table is always available as `df`. Read the generated request with `print(task['prompt'])`, explore the data, then produce the result the prompt asks for.

### What to do
1. Choose a difficulty in the left panel. Change it anytime to get a fresh challenge.
2. Inspect `df` and the task prompt.
3. Write pandas code that answers the prompt.
4. Run the notebook and confirm the check passes.

If the prompt asks for a single value, assign it to `answer`. If it asks for a table of rows, assign that table to `df`.
"""

SOFT_SKILL_PROMPT = (
	"Give an example of when a business would want a query like the one you just solved "
	"(who would use it, and what decision it could support). "
	"Alternatively, describe a different query on this kind of data that you think would be "
	"more valuable, and briefly explain why."
)

EVALUATION_RULES = {
	"required_variables": ["df", "task"],
	"assertions": [
		"pandas_intro_task_passes(task, df=df, answer=answer)",
	],
	"success_message": "Nice work. Your solution matches the pandas task prompt.",
	"failure_message": (
		"Your solution does not match the expected result yet. "
		"Re-read the prompt: use `answer` for a single summary value, or `df` for a filtered table."
	),
}


def update_pandas_introduction(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	exercise = Exercise.objects.filter(slug="pandas-introduction").first()
	if not exercise:
		return
	exercise.intro_markdown = PANDAS_INTRO_MARKDOWN
	exercise.soft_skill_prompt = SOFT_SKILL_PROMPT
	exercise.evaluation_rules = EVALUATION_RULES
	exercise.graphic_markup = (
		"<p class='text-sm text-slate-600 dark:text-slate-300'>"
		"The panel below shows a formatted <code>df.head()</code> "
		"preview from your latest notebook run.</p>"
	)
	exercise.save(
		update_fields=[
			"intro_markdown",
			"soft_skill_prompt",
			"evaluation_rules",
			"graphic_markup",
		]
	)


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):
	dependencies = [
		("exercises", "0012_remove_course_lesson_fields"),
	]

	operations = [
		migrations.RunPython(update_pandas_introduction, noop_reverse),
	]
