"""Migrate analytics exercises to typed evaluation_rules (v2 rubric graders)."""

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
	"data-cleaning-messy-dataset": _rules(
		"Nice work. Your cleaned table matches the tidy schema.",
		"The cleaned table does not match yet. Fix headers, types, and joins step by step.",
		[
			{"id": "required_df", "type": "required_variable", "variable": "df", "section": "core", "soft": True},
			{"id": "required_task", "type": "required_variable", "variable": "task", "section": "core", "soft": True},
			{
				"id": "no_nulls",
				"type": "invariant",
				"name": "no_nulls",
				"variable": "df",
				"section": "approach",
				"soft": True,
				"next_action": "Remove remaining missing values after cleaning.",
			},
			{
				"id": "messy_core",
				"type": "assertion",
				"expression": "messy_dataset_passes(df, task)",
				"section": "core",
				"next_action": "Align columns to the expected tidy schema, then repair values and merge extras.",
			},
			{
				"id": "cleanup_approach",
				"type": "ast_process",
				"section": "approach",
				"require_any": ["dropna", "drop_duplicates", "rename", "merge", "map", "astype", "to_numeric"],
				"fragile": True,
				"next_action": "Use cleaning APIs (dropna/drop_duplicates/merge/map) rather than rewriting the table by hand.",
			},
		],
	),
	"ab-testing-conditional-probability": _rules(
		"Nice work. Your A/B or Bayes conclusion matches the expected decision.",
		"Your decision does not match yet. Re-check the test or Bayes calculation.",
		[
			{"id": "required_df", "type": "required_variable", "variable": "df", "section": "core", "soft": True},
			{"id": "required_task", "type": "required_variable", "variable": "task", "section": "core", "soft": True},
			{
				"id": "ab_core",
				"type": "assertion",
				"expression": "ab_testing_passes(task, different=different, relevant=relevant, answer=answer, p_value=p_value)",
				"section": "core",
				"next_action": "Compute the required decision variables (`different` / `answer` / `relevant`) from the scenario.",
			},
			{
				"id": "stats_approach",
				"type": "ast_process",
				"section": "approach",
				"when_difficulty": ["easy", "hard"],
				"require_any": ["welch_ttest", "ttest", "mean"],
				"fragile": True,
				"next_action": "Use welch_ttest (or an equivalent mean comparison) for the A/B decision.",
			},
		],
	),
	"descriptive-statistics": _rules(
		"Nice work. Your descriptive statistics match the expected summaries.",
		"Your answers do not match yet. Recompute the requested summaries.",
		[
			{"id": "required_df", "type": "required_variable", "variable": "df", "section": "core", "soft": True},
			{"id": "required_task", "type": "required_variable", "variable": "task", "section": "core", "soft": True},
			{"id": "required_answer", "type": "required_variable", "variable": "answer", "section": "core", "soft": True, "next_action": "Store results in `answer` (dict of q1/q2/...)."},
			{
				"id": "desc_core",
				"type": "assertion",
				"expression": "descriptive_statistics_passes(task, answer=answer, plotted=plotted)",
				"section": "core",
				"next_action": "Fill every required `answer` key from df summaries; set `plotted=True` when a plot is required.",
			},
			{
				"id": "summary_approach",
				"type": "ast_process",
				"section": "approach",
				"require_any": ["mean", "median", "std", "var", "mode", "corr", "groupby", "hist", "boxplot", "imshow"],
				"fragile": True,
				"next_action": "Compute summaries with pandas/numpy stats APIs rather than hard-coding.",
			},
		],
	),
	"clean-messy-dataset": _rules(
		"Nice work. Your imputation passes the difficulty-aware checks.",
		"Your fill does not pass yet. Remove NA values and refine the imputation approach.",
		[
			{"id": "required_df", "type": "required_variable", "variable": "df", "section": "core", "soft": True},
			{"id": "required_baseline", "type": "required_variable", "variable": "df_baseline", "section": "core", "soft": True},
			{"id": "required_target", "type": "required_variable", "variable": "target", "section": "core", "soft": True},
			{"id": "required_outcome", "type": "required_variable", "variable": "outcome", "section": "core", "soft": True},
			{
				"id": "no_nulls",
				"type": "invariant",
				"name": "no_nulls",
				"variable": "df",
				"section": "core",
				"soft": True,
				"next_action": "Fill every missing value in `df` before evaluating.",
			},
			{
				"id": "missing_core",
				"type": "assertion",
				"expression": "missing_values_imputation_passes(df, df_baseline, target, outcome, data)",
				"section": "core",
				"next_action": "On medium/hard, impute using the outcome variable (groupby/transform), not only a global constant.",
			},
			{
				"id": "grouped_fill_approach",
				"type": "ast_process",
				"section": "approach",
				"when_difficulty": ["medium", "hard"],
				"require_any": ["groupby", "transform", "merge"],
				"fragile": True,
				"next_action": "Use groupby/transform (or a merge of group statistics) so fills depend on another column.",
			},
		],
	),
}


def apply_rules(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	for slug, rules in RULES.items():
		Exercise.objects.filter(slug=slug).update(evaluation_rules=rules)


def noop_reverse(apps, schema_editor):
	# Legacy rules remain recoverable from earlier migrations if needed.
	pass


class Migration(migrations.Migration):

	dependencies = [
		("exercises", "0019_activate_descriptive_statistics"),
	]

	operations = [
		migrations.RunPython(apply_rules, noop_reverse),
	]
