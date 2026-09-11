from copy import deepcopy

from django.db import migrations


PANDAS_INTRO_MARKDOWN = """Practice core pandas skills by turning a plain-language request into a dataframe.

The working table is always available as `df`. Inspect the task with `print(task['prompt'])`, then transform `df` so it matches the prompt.

### What to do
1. Choose a difficulty in the left panel.
2. Inspect `df` and the generated task prompt.
3. Transform `df` so it matches the prompt.
4. Run the notebook and confirm the match check passes.

### Difficulty levels
- **Easy**: select between 1 and 4 columns.
- **Medium**: select columns and apply 1-2 boolean conditions.
- **Hard**: medium requirements plus sorting, grouping, or a string selection such as names that start with A-E.
"""

STARTER_CODE = """# %%
# df and task are preloaded.
# print(task['prompt'])
# df.head()
# %%
# Transform df to match the task prompt.
# df = df[['name', 'age']]
df.head()
"""


def update_exercise_dataframe_naming(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")

    pandas_intro = Exercise.objects.filter(slug="pandas-introduction").first()
    if pandas_intro:
        data_definition = deepcopy(pandas_intro.data_definition or {})
        data_definition["dataframe_source"] = "pandas_intro"
        initial = dict(data_definition.get("initial_data") or {})
        initial["dataframe_source"] = "pandas_intro"
        data_definition["initial_data"] = initial
        for key in ("feature_choices", "difficulty_choices"):
            if key in data_definition:
                data_definition[key] = [
                    {k: v for k, v in dict(choice).items() if k != "description"}
                    for choice in data_definition.get(key) or []
                ]
        pandas_intro.data_definition = data_definition
        pandas_intro.intro_markdown = PANDAS_INTRO_MARKDOWN
        pandas_intro.starter_code = STARTER_CODE
        pandas_intro.evaluation_rules = {
            "required_variables": ["df", "task"],
            "assertions": ["dataframes_match(df, task['expected_df'])"],
            "success_message": "Nice work. Your dataframe matches the pandas task prompt.",
            "failure_message": "df does not match the expected dataframe yet. Re-read the prompt and adjust your column selection, filters, and any hard-mode step.",
        }
        pandas_intro.graphic_markup = (
            "<p class='text-sm text-slate-600 dark:text-slate-300'>"
            "The panel below shows a formatted <code>df.head()</code> "
            "preview from your latest notebook run.</p>"
        )
        pandas_intro.save()

    missing = Exercise.objects.filter(slug="fill-missing-values-generated-data").first()
    if missing:
        data_definition = deepcopy(missing.data_definition or {})
        data_definition["dataframe_source"] = "missing_values"
        initial = dict(data_definition.get("initial_data") or {})
        initial["dataframe_source"] = "missing_values"
        initial.setdefault("difficulty", "easy")
        initial.setdefault("seed", 42)
        initial.setdefault("data_field", "biostatistics")
        initial.setdefault("dataset_file", "01_diabetes.parquet")
        data_definition["initial_data"] = initial
        data_definition["difficulty_choices"] = [
            {"label": "Easy", "value": "easy"},
            {"label": "Medium", "value": "medium"},
            {"label": "Hard", "value": "hard"},
        ]
        data_definition["feature_choices"] = [
            {"label": "Easy", "value": "easy"},
            {"label": "Medium", "value": "medium"},
            {"label": "Hard", "value": "hard"},
        ]
        for key in ("mode_choices", "real_dataset_choices"):
            data_definition.pop(key, None)
        missing.data_definition = data_definition
        missing.title = "Fill Missing Values"
        missing.intro_markdown = """You are given a real dataset in `df` with missing values. Fill the missing values and verify the dataset has no NA values left.

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
        missing.starter_code = ""
        missing.evaluation_rules = {
            "required_variables": ["df", "df_baseline", "target", "outcome"],
            "assertions": [
                "missing_values_imputation_passes(df, df_baseline, target, outcome, data)",
            ],
            "success_message": "Great job. Your imputation matches the selected difficulty.",
            "failure_message": "Your fill does not yet match this difficulty. Remove all NA values and use a stronger imputation approach.",
        }
        missing.graphic_markup = (
            "<p class='text-sm text-slate-600 dark:text-slate-300'>"
            "The chart below uses the selected outcome variable against the target column.</p>"
        )
        missing.save()

    quality = Exercise.objects.filter(slug="clean-messy-dataset").first()
    if quality:
        data_definition = deepcopy(quality.data_definition or {})
        data_definition["dataframe_source"] = "data_quality"
        initial = dict(data_definition.get("initial_data") or {})
        initial["dataframe_source"] = "data_quality"
        data_definition["initial_data"] = initial
        if not data_definition.get("feature_choices"):
            data_definition["feature_choices"] = [
                {"label": "Easy", "value": "easy"},
                {"label": "Medium", "value": "medium"},
                {"label": "Hard", "value": "hard"},
            ]
        data_definition["difficulty_choices"] = [
            {"label": "Easy", "value": "easy"},
            {"label": "Medium", "value": "medium"},
            {"label": "Hard", "value": "hard"},
        ]
        quality.data_definition = data_definition
        quality.intro_markdown = """You are given a messy dataset in `df` that has been intentionally corrupted using a seeded generator. Clean `df` before analysis.

### What to do
1. Inspect `df`.
2. Correct bad values and inconsistent labels.
3. Remove duplicate rows if present.
4. Convert text values to the correct numeric dtypes.
5. Confirm `df` is valid and ready for analysis.

This task is generated from a seed, so the same seed repeats the same problem set on the same clean source data.
"""
        quality.evaluation_rules = {
            "required_variables": ["df"],
            "assertions": [
                "df.isna().sum().sum() == 0",
                "df.duplicated().sum() == 0",
                "pd.api.types.is_numeric_dtype(df['sales'])",
                "pd.api.types.is_numeric_dtype(df['score'])",
                "df['status'].str.lower().isin(['active', 'inactive']).all()",
            ],
            "success_message": "Nice work. The generated dataset was cleaned, deduplicated, and restored to a valid state.",
            "failure_message": "df still contains generated quality issues. Repair values, standardize labels, remove duplicates, and convert numeric columns back to valid types.",
        }
        quality.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0004_seed_pandas_introduction_exercise"),
    ]

    operations = [
        migrations.RunPython(update_exercise_dataframe_naming, noop_reverse),
    ]
