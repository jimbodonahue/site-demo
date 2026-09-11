from copy import deepcopy

from django.db import migrations


INTRO_MARKDOWN = """You are given a Data Zoo sample in `df` where some values in one numeric column are missing. Your job is to fill them in thoughtfully before analysis.

The working table is always available as `df`. A second copy is available as `df_baseline` if you want to revert your edits. The columns to focus on are named in `target` and `outcome`.

### What to do
1. Choose a **topic** and **difficulty** in the left panel.
2. Inspect `df`, `target`, and `outcome`.
3. Fill the missing values in the `target` column.
4. Confirm `df` has no remaining missing values.

Changing difficulty or topic resets the notebook with a fresh sample.
"""


def update_data_cleaning_mechanics(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    exercise = Exercise.objects.filter(slug="clean-messy-dataset").first()
    if not exercise:
        return

    data_definition = deepcopy(exercise.data_definition or {})
    data_definition["dataframe_source"] = "data_quality"
    initial = dict(data_definition.get("initial_data") or {})
    initial.update(
        {
            "seed": initial.get("seed", 42),
            "difficulty": initial.get("difficulty") or "easy",
            "selected_feature": initial.get("selected_feature")
            or initial.get("difficulty")
            or "easy",
            "dataframe_source": "data_quality",
            "data_field": initial.get("data_field") or "marketing",
            "topic": initial.get("topic") or initial.get("data_field") or "marketing",
            "n_rows": initial.get("n_rows") or 80,
        }
    )
    data_definition["initial_data"] = initial
    exercise.data_definition = data_definition
    exercise.intro_markdown = INTRO_MARKDOWN
    exercise.evaluation_rules = {
        "required_variables": ["df", "df_baseline", "target", "outcome"],
        "assertions": [
            "missing_values_imputation_passes(df, df_baseline, target, outcome, data)",
        ],
        "success_message": "Great job. Your imputation looks solid for this scenario.",
        "failure_message": "Your fill does not yet pass evaluation. Remove all NA values and refine your approach.",
    }
    exercise.graphic_markup = (
        "<p class='text-sm text-slate-600'>"
        "The chart below uses the selected outcome variable against the target column."
        "</p>"
    )
    exercise.save()

    # Remove difficulty spoilers from the parquet-based Fill Missing Values exercise too.
    fill = Exercise.objects.filter(slug="fill-missing-values-generated-data").first()
    if fill:
        fill.intro_markdown = """You are given a real dataset in `df` with missing values. Fill the missing values and verify the dataset has no NA values left.

The working table is always available as `df`. A second copy is available as `df_baseline` if you want to revert your edits. The columns to focus on are named in `target` and `outcome`.

### What to do
1. Choose a difficulty in the left panel.
2. Inspect `df`, `target`, and `outcome`.
3. Fill the missing values in the `target` column.
4. Confirm `df` has no remaining missing values.
"""
        fill.evaluation_rules = {
            **(fill.evaluation_rules or {}),
            "success_message": "Great job. Your imputation looks solid for this scenario.",
            "failure_message": "Your fill does not yet pass evaluation. Remove all NA values and refine your approach.",
        }
        fill.save(update_fields=["intro_markdown", "evaluation_rules", "updated_at"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("exercises", "0008_rename_data_cleaning_missing_values"),
    ]

    operations = [
        migrations.RunPython(update_data_cleaning_mechanics, noop_reverse),
    ]
