from copy import deepcopy

from django.db import migrations


DATA_SCIENCE_SECTORS = [
    "biostatistics",
    "econometrics",
    "agriculture",
    "finance",
    "marketing",
    "healthcare",
    "manufacturing",
    "energy",
    "public_policy",
    "education",
    "environmental_science",
    "transportation",
]

TOPIC_CHOICES = [
    {"label": sector.replace("_", " ").title(), "value": sector}
    for sector in DATA_SCIENCE_SECTORS
]


def update_clean_messy_exercise(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")

    exercise = Exercise.objects.filter(slug="clean-messy-dataset").first()
    if not exercise:
        return

    exercise.title = "Data Cleaning: Missing Values"
    data_definition = deepcopy(exercise.data_definition or {})
    data_definition["dataframe_source"] = "data_quality"
    data_definition["topic_choices"] = TOPIC_CHOICES
    data_definition["feature_choices"] = [
        {"label": "Easy", "value": "easy"},
        {"label": "Medium", "value": "medium"},
        {"label": "Hard", "value": "hard"},
    ]
    data_definition["difficulty_choices"] = list(data_definition["feature_choices"])
    initial = dict(data_definition.get("initial_data") or {})
    initial.update(
        {
            "seed": initial.get("seed", 42),
            "difficulty": initial.get("difficulty") or "medium",
            "selected_feature": initial.get("selected_feature") or initial.get("difficulty") or "medium",
            "dataframe_source": "data_quality",
            "data_field": initial.get("data_field") or "marketing",
            "topic": initial.get("topic") or initial.get("data_field") or "marketing",
            "n_rows": initial.get("n_rows", 40),
        }
    )
    data_definition["initial_data"] = initial
    exercise.data_definition = data_definition
    exercise.intro_markdown = """You are given a messy Data Zoo sample in `df` that has been intentionally corrupted using a seeded generator. Clean `df` before analysis.

### What to do
1. Choose a **topic** and **difficulty** in the left panel.
2. Inspect `df` for missing values, duplicates, and corrupted types.
3. Repair bad values and inconsistent labels.
4. Remove duplicate rows if present.
5. Convert columns back to valid numeric dtypes where needed.
6. Confirm `df` is ready for analysis.

Changing difficulty or topic resets the notebook with a fresh corrupted sample.
"""
    exercise.evaluation_rules = {
        "required_variables": ["df", "numeric_columns"],
        "assertions": [
            "data_quality_cleanup_passes(df, numeric_columns)",
        ],
        "success_message": "Nice work. Missing values, duplicates, and corrupted numeric columns look cleaned up.",
        "failure_message": "df still has quality issues. Remove nulls and duplicates, and restore numeric columns to numeric dtypes.",
    }
    exercise.graphic_markup = (
        "<p class='text-sm text-slate-600'>Pick a Data Zoo topic, then clean the corrupted sample shown in the notebook.</p>"
    )
    exercise.save()


def revert_clean_messy_exercise(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    exercise = Exercise.objects.filter(slug="clean-messy-dataset").first()
    if not exercise:
        return
    exercise.title = "Clean a Messy Dataset"
    exercise.save(update_fields=["title"])


class Migration(migrations.Migration):

    dependencies = [
        ("exercises", "0007_seed_soft_skill_prompts"),
    ]

    operations = [
        migrations.RunPython(update_clean_messy_exercise, revert_clean_messy_exercise),
    ]
