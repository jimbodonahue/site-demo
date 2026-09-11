from django.db import migrations


INTRO_MARKDOWN = """You are given a real dataset in `df` with missing values. Fill the missing values and verify the dataset has no NA values left.

The working table is always available as `df`. A second copy is available as `df_baseline` if you want to revert your edits. The columns to focus on are named in `target` and `outcome`.

### What to do
1. Choose a difficulty in the left panel.
2. Inspect `df`, `target`, and `outcome`.
3. Fill the missing values in `df` using an approach that matches the selected difficulty.
4. Confirm the progress check passes.

Tips:
- Easy: a simple column fill can work.
- Medium: use the second float column (`outcome`) to guide the fill.
- Hard: also account for where values appear to be missing in the target distribution (for example by inspecting skew after observing the gaps).
- Use `df = df_baseline.copy()` if you want to start over without resetting the whole exercise.

Your scenario settings are saved privately with your account so you can repeat this exercise later.
"""


def seed_missing_values_exercise(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    Module = apps.get_model("courses", "Module")
    Lesson = apps.get_model("courses", "Lesson")
    Exercise = apps.get_model("exercises", "Exercise")

    course, _ = Course.objects.get_or_create(
        slug="data-cleaning-fundamentals",
        defaults={
            "title": "Data Cleaning Fundamentals",
            "summary": "Learn practical data cleaning and validation techniques.",
            "overview_markdown": "Start with missing values, then move to outliers and scaling.",
            "order": 50,
            "published": True,
        },
    )

    module, _ = Module.objects.get_or_create(
        course=course,
        slug="missing-data-basics",
        defaults={
            "title": "Missing Data Basics",
            "summary": "Understand and fix missing values in selected datasets.",
            "order": 10,
            "published": True,
        },
    )

    lesson, _ = Lesson.objects.get_or_create(
        module=module,
        slug="fill-missing-values",
        defaults={
            "title": "Fill Missing Values",
            "summary": "Use simple imputation strategies before modeling.",
            "body_markdown": "This lesson introduces basic missing-value treatment for tabular data.",
            "order": 10,
            "published": True,
        },
    )

    Exercise.objects.update_or_create(
        slug="fill-missing-values-generated-data",
        defaults={
            "course": course,
            "lesson": lesson,
            "title": "Fill Missing Values",
            "intro_markdown": INTRO_MARKDOWN,
            "starter_code": "",
            "allowed_imports": ["numpy", "pandas", "matplotlib.pyplot"],
            "data_definition": {
                "dataframe_source": "missing_values",
                "initial_data": {
                    "seed": 42,
                    "difficulty": "easy",
                    "dataframe_source": "missing_values",
                    "data_field": "biostatistics",
                    "dataset_file": "01_diabetes.parquet",
                },
                "difficulty_choices": [
                    {"label": "Easy", "value": "easy"},
                    {"label": "Medium", "value": "medium"},
                    {"label": "Hard", "value": "hard"},
                ],
                "feature_choices": [
                    {"label": "Easy", "value": "easy"},
                    {"label": "Medium", "value": "medium"},
                    {"label": "Hard", "value": "hard"},
                ],
            },
            "evaluation_rules": {
                "required_variables": ["df", "df_baseline", "target", "outcome"],
                "assertions": [
                    "missing_values_imputation_passes(df, df_baseline, target, outcome, data)",
                ],
                "success_message": "Great job. Your imputation matches the selected difficulty.",
                "failure_message": "Your fill does not yet match this difficulty. Remove all NA values and use a stronger imputation approach.",
            },
            "graphic_markup": (
                "<p class='text-sm text-slate-600 dark:text-slate-300'>"
                "The chart below uses the selected outcome variable against the target column.</p>"
            ),
            "order": 20,
            "published": True,
        },
    )


def unseed_missing_values_exercise(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(slug="fill-missing-values-generated-data").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0001_initial"),
        ("exercises", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_missing_values_exercise, unseed_missing_values_exercise),
    ]
