from django.db import migrations


INTRO_MARKDOWN = """Practice transforming a product table into analysis-ready pieces.

The working table is available as `df`. Read the request with `print(task['prompt'])`, inspect the columns, then produce the dataframes the prompt asks for.

On **hard** mode you will sometimes also get a lookup table as `df_extra` that must be joined in before you build `df0` / `df1` / `df2` (ecommerce uses real Olist order items + products).

### What to do
1. Choose a difficulty in the left panel. Change it anytime for a fresh challenge.
2. Inspect `df` (and `df_extra` when present) plus the task prompt.
3. Build `df0`, `df1`, and `df2` to match the request.
4. Run the notebook and confirm the check passes.

Tip: start with `df.head()`. Encoding drills often need `size_raw` / `satisfaction` / `in_stock`; join drills need `df.merge(...)`.
"""


def update_data_transformation(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	exercise = Exercise.objects.filter(slug="data-transformation").first()
	if not exercise:
		return

	exercise.intro_markdown = INTRO_MARKDOWN
	rules = dict(exercise.evaluation_rules or {})
	graders = list(rules.get("graders") or [])
	for check in graders:
		if check.get("id") == "encoding_approach":
			require_any = list(check.get("require_any") or [])
			for name in ("merge", "join"):
				if name not in require_any:
					require_any.append(name)
			check["require_any"] = require_any
			check["next_action"] = (
				"Use an encoding API such as map/apply/get_dummies, "
				"or merge/join when the hard prompt includes `df_extra`."
			)
	rules["graders"] = graders
	rules["failure_message"] = (
		"df0/df1/df2 do not match yet. Check filters, encodings, and joins when `df_extra` is present."
	)
	exercise.evaluation_rules = rules
	exercise.save()


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):
	dependencies = [
		("exercises", "0020_typed_evaluation_rules"),
	]

	operations = [
		migrations.RunPython(update_data_transformation, noop_reverse),
	]
