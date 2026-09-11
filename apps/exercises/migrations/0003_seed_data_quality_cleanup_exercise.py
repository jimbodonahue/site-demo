from django.db import migrations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from apps.exercises.data_quality import introduce_data_quality_issues


def seed_data_quality_cleanup_exercise(apps, schema_editor):
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
        slug="data-quality-repair",
        defaults={
            "title": "Data Quality Repair",
            "summary": "Fix messy values, duplicates, and inconsistent records before analysis.",
            "order": 20,
            "published": True,
        },
    )

    lesson, _ = Lesson.objects.get_or_create(
        module=module,
        slug="clean-messy-dataset",
        defaults={
            "title": "Clean a Messy Dataset",
            "summary": "Repair common spreadsheet and CSV issues before modeling.",
            "body_markdown": "This lesson focuses on dirty data: OCR-style substitutions, duplicates, type coercion, and inconsistent labels.",
            "order": 20,
            "published": True,
        },
    )

    starter_code = """# %%
# --- Use a reusable generator on any clean dataset ---
# The goal is to reproduce a dirty version of a known-clean dataframe.
# We can control difficulty and seed to create repeatable tasks.

rng = np.random.default_rng(data.get('seed', 42))

records = [
    {"customer_id": "C-001", "region": "North", "channel": "email", "status": "active", "sales": 1200, "score": 8.7},
    {"customer_id": "C-002", "region": "South", "channel": "sms", "status": "active", "sales": 980, "score": 7.4},
    {"customer_id": "C-003", "region": "West", "channel": "phone", "status": "inactive", "sales": 640, "score": 6.1},
    {"customer_id": "C-004", "region": "East", "channel": "email", "status": "active", "sales": 1350, "score": 9.2},
    {"customer_id": "C-005", "region": "North", "channel": "email", "status": "active", "sales": 810, "score": 5.8},
    {"customer_id": "C-006", "region": "South", "channel": "call_center", "status": "active", "sales": 1180, "score": 6.5},
    {"customer_id": "C-007", "region": "West", "channel": "sms", "status": "active", "sales": 780, "score": 7.9},
    {"customer_id": "C-008", "region": "East", "channel": "email", "status": "active", "sales": 900, "score": 8.1},
    {"customer_id": "C-009", "region": "North", "channel": "email", "status": "active", "sales": 850, "score": 8.4},
    {"customer_id": "C-010", "region": "South", "channel": "phone", "status": "active", "sales": 1100, "score": 6.3},
]

clean_df = pd.DataFrame(records)

# Reproducible issue generation by seed and difficulty
# Easy: 3-5 issues, Medium: 6-9, Hard: 12-15
# Each issue is tracked in issue_log so you can inspect exactly what was changed.
dirty_df, issue_log = introduce_data_quality_issues(
    clean_df,
    difficulty=data.get('difficulty', 'medium'),
    seed=data.get('seed', 42),
)

print('Difficulty:', data.get('difficulty', 'medium'))
print('Seed:', data.get('seed', 42))
print('Issue count:', len(issue_log))
print(issue_log)
dirty_df.head()
# %%
# TODO for students:
# 1) Fix OCR-like replacements: O -> 0, ! -> 1, etc.
# 2) Remove duplicate rows.
# 3) Convert weird type strings like '1,200' or 'nan' to actual numbers.
# 4) Fix categorical inconsistencies and null values.
# 5) Return a clean dataframe ready for analysis.

clean_df = dirty_df.copy()

# Example starting points:
# clean_df['sales'] = clean_df['sales'].astype(str).str.replace(',', '', regex=False)
# clean_df['sales'] = clean_df['sales'].replace({'O': '0', 'o': '0', '!': '1', 'N/A': np.nan, 'nan': np.nan})
# clean_df['sales'] = pd.to_numeric(clean_df['sales'], errors='coerce')
# clean_df['channel'] = clean_df['channel'].str.lower().str.replace(' ', '_', regex=False)
# clean_df['status'] = clean_df['status'].str.lower()
# clean_df = clean_df.drop_duplicates().reset_index(drop=True)
# clean_df = clean_df.dropna(subset=['customer_id', 'sales', 'score']).reset_index(drop=True)

clean_df.head()
# %%
plt.figure(figsize=(6, 4))
plt.scatter(clean_df['sales'], clean_df['score'], alpha=0.7)
plt.title('Sales vs. Score after cleanup')
plt.xlabel('Sales')
plt.ylabel('Score')
plt.tight_layout()

rows_after_cleaning = len(clean_df)
missing_after = int(clean_df.isna().sum().sum())
print('Rows after cleaning:', rows_after_cleaning)
print('Missing values after cleaning:', missing_after)
missing_after
"""

    Exercise.objects.update_or_create(
        slug="clean-messy-dataset",
        defaults={
            "course": course,
            "lesson": lesson,
            "title": "Clean a Messy Dataset",
            "intro_markdown": """You are given a messy dataset in `df` that has been intentionally corrupted using a seeded generator. Clean `df` before analysis.

### What to do
1. Inspect `df`.
2. Correct bad values and inconsistent labels.
3. Remove duplicate rows if present.
4. Convert text values to the correct numeric dtypes.
5. Confirm `df` is valid and ready for analysis.

This task is generated from a seed, so the same seed repeats the same problem set on the same clean source data.
""",
            "starter_code": starter_code,
            "allowed_imports": ["numpy", "pandas", "matplotlib.pyplot"],
            "data_definition": {
                "dataframe_source": "data_quality",
                "initial_data": {
                    "seed": 42,
                    "difficulty": "medium",
                    "dataframe_source": "data_quality",
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
			},
			"graphic_markup": "<p class='text-sm text-slate-600'>This chart updates from your cleaned sales and score data.</p>",
			"order": 30,
			"published": True,
		},
	)


def unseed_data_quality_cleanup_exercise(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(slug="clean-messy-dataset").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0001_initial"),
        ("exercises", "0002_seed_missing_values_exercise"),
    ]

    operations = [
        migrations.RunPython(
            seed_data_quality_cleanup_exercise,
            unseed_data_quality_cleanup_exercise,
        ),
    ]
