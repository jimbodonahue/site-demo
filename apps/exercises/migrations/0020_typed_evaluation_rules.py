"""Migrate pandas-introduction and data-transformation to typed evaluation_rules."""

from django.db import migrations


COMMON_META = {
	"version": 2,
	"second_seed_recheck": {"enabled": True, "seed_offset": 10007},
	"soft_skill": {"required_for_full_completion": True, "min_chars": 40, "min_words": 8},
}


def _rules(success: str, failure: str, graders: list) -> dict:
	return {
		**COMMON_META,
		"success_message": success,
		"failure_message": failure,
		"graders": graders,
	}


RULES = {
	"pandas-introduction": _rules(
		"Nice work. Your pandas result matches the task.",
		"Your solution does not match yet. Follow the next action below.",
		[
			{
				"id": "required_df",
				"type": "required_variable",
				"variable": "df",
				"section": "core",
				"soft": True,
				"next_action": "Keep working in `df` (and `answer` on summary tasks).",
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
				"id": "pandas_core",
				"type": "assertion",
				"expression": "pandas_intro_task_passes(task, df=df, answer=answer)",
				"section": "core",
				"soft": False,
				"next_action": "Recompute from `df` — assign `answer` for summaries or filter/sort `df` for subset tasks.",
				"failure_message": "Result does not match the task yet.",
			},
		],
	),
	"data-transformation": _rules(
		"Nice work. Your transformed frames match the expected bands/encodings.",
		"df0/df1/df2 do not match yet. Check filters and encodings.",
		[
			{"id": "required_df", "type": "required_variable", "variable": "df", "section": "core", "soft": True},
			{"id": "required_df0", "type": "required_variable", "variable": "df0", "section": "core", "soft": True, "next_action": "Assign the first band/encoding result to `df0`."},
			{"id": "required_df1", "type": "required_variable", "variable": "df1", "section": "core", "soft": True, "next_action": "Assign the second result to `df1`."},
			{"id": "required_df2", "type": "required_variable", "variable": "df2", "section": "core", "soft": True, "next_action": "Assign the third result to `df2`."},
			{
				"id": "transform_core",
				"type": "assertion",
				"expression": "data_transformation_passes(task, df0=df0, df1=df1, df2=df2)",
				"section": "core",
				"next_action": "Rebuild df0/df1/df2 from the prompt rules; reset_index(drop=True) when needed.",
			},
			{
				"id": "encoding_approach",
				"type": "ast_process",
				"section": "approach",
				"when_difficulty": ["medium", "hard"],
				"require_any": ["map", "apply", "get_dummies", "replace", "astype"],
				"fragile": True,
				"next_action": "Use an encoding API such as map/apply/get_dummies on medium/hard.",
			},
		],
	),
}


def apply_rules(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	for slug, rules in RULES.items():
		Exercise.objects.filter(slug=slug).update(evaluation_rules=rules)


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):

	dependencies = [
		("exercises", "0019_lite_catalog"),
	]

	operations = [
		migrations.RunPython(apply_rules, noop_reverse),
	]
