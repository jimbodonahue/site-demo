from django.db import migrations


def seed_pandas_introduction_exercise(apps, schema_editor):
    Course = apps.get_model("courses", "Course")
    Module = apps.get_model("courses", "Module")
    Lesson = apps.get_model("courses", "Lesson")
    Exercise = apps.get_model("exercises", "Exercise")

    course, _ = Course.objects.get_or_create(
        slug="pandas-fundamentals",
        defaults={
            "title": "Pandas Fundamentals",
            "summary": "Learn core pandas skills for selecting, filtering, and summarizing tabular data.",
            "overview_markdown": "Start with column selection, then move to boolean filters, sorting, grouping, and string selection.",
            "order": 40,
            "published": True,
        },
    )

    module, _ = Module.objects.get_or_create(
        course=course,
        slug="dataframe-basics",
        defaults={
            "title": "DataFrame Basics",
            "summary": "Practice reading prompts and building the matching pandas dataframe.",
            "order": 10,
            "published": True,
        },
    )

    lesson, _ = Lesson.objects.get_or_create(
        module=module,
        slug="select-and-filter",
        defaults={
            "title": "Select and Filter Rows",
            "summary": "Turn a plain-language request into a pandas dataframe.",
            "body_markdown": "This lesson introduces column selection, boolean filtering, sorting, grouping, and simple string filters.",
            "order": 10,
            "published": True,
        },
    )

    starter_code = """# %%
# df and task are preloaded.
# print(task['prompt'])
# df.head()
# %%
# Transform df to match the task prompt.
df.head()
"""

    Exercise.objects.update_or_create(
        slug="pandas-introduction",
        defaults={
            "course": course,
            "lesson": lesson,
            "title": "Pandas Introduction",
            "intro_markdown": """Practice core pandas skills by turning a plain-language request into a dataframe.

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
""",
            "starter_code": starter_code,
            "allowed_imports": ["numpy", "pandas", "matplotlib.pyplot"],
            "data_definition": {
                "dataframe_source": "pandas_intro",
                "initial_data": {
                    "seed": 42,
                    "difficulty": "easy",
                    "n_rows": 80,
                    "dataframe_source": "pandas_intro",
                },
                "feature_choices": [
					{
						"label": "Easy",
						"value": "easy",
					},
					{
						"label": "Medium",
						"value": "medium",
					},
					{
						"label": "Hard",
						"value": "hard",
					},
				],
				"difficulty_choices": [
					{"label": "Easy", "value": "easy"},
					{"label": "Medium", "value": "medium"},
					{"label": "Hard", "value": "hard"},
				],
			},
			"evaluation_rules": {
				"required_variables": ["df", "task"],
				"assertions": [
					"dataframes_match(df, task['expected_df'])",
				],
				"success_message": "Nice work. Your dataframe matches the pandas task prompt.",
				"failure_message": "df does not match the expected dataframe yet. Re-read the prompt and adjust your column selection, filters, and any hard-mode step.",
			},
			"graphic_markup": "<p class='text-sm text-slate-600 dark:text-slate-300'>The panel below shows a formatted <code>df.head()</code> preview from your latest notebook run.</p>",
			"order": 10,
			"published": True,
		},
	)


def unseed_pandas_introduction_exercise(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(slug="pandas-introduction").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0001_initial"),
        ("exercises", "0003_seed_data_quality_cleanup_exercise"),
    ]

    operations = [
        migrations.RunPython(
            seed_pandas_introduction_exercise,
            unseed_pandas_introduction_exercise,
        ),
    ]
