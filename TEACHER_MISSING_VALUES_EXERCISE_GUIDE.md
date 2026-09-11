# Teacher Guide: Missing Values Exercise

This guide explains, in plain language, how the "Fill Missing Values" exercise was built and how you can create another one.

## What was built

A new exercise was added where students:

1. Generate data with missing values.
2. Fill in the missing values.
3. See a scatter plot with a regression line in the right panel.
4. Pass the check only when there are no `NA` values left.

The exercise title is:

- Fill Missing Values in Generated Data

The exercise URL slug is:

- `fill-missing-values-generated-data`

## Files used

These are the main files used for this feature:

- `apps/exercises/migrations/0002_seed_missing_values_exercise.py`
- `templates/exercises/exercise_detail.html`
- `apps/exercises/tests.py`

And these existing files support it:

- `apps/exercises/models.py`
- `apps/exercises/views.py`
- `apps/exercises/services.py`

## What each file does

### 1) `apps/exercises/migrations/0002_seed_missing_values_exercise.py`

This file creates the example exercise content in the database.

It sets:

- The exercise title and intro.
- The starter notebook code.
- Allowed libraries (`numpy`, `pandas`, `matplotlib.pyplot`).
- Data settings (seed, number of points, missingness level).
- Left-panel feature options (low/medium/high missingness).
- Evaluation rule that checks for no missing values.

### 2) `templates/exercises/exercise_detail.html`

This is the student page template.

It shows:

- Left column: data features.
- Middle column: notebook coding cells.
- Right column: graphic area and progress/evaluation.

For this exercise, the template now also includes a live plot area in the right panel. When students run code that creates a figure, the newest figure appears there.

### 3) `apps/exercises/tests.py`

This verifies that:

- The seeded exercise exists.
- Filling missing values can pass the checks.
- The run produces a figure.
- The right-panel live plot container is present on the page.

## How the exercise logic works

### Generated data

The first notebook cell generates student-like data (`study_hours`, `score`) and intentionally inserts missing values based on the selected scenario.

### Student task

In the second cell, students fill missing values in `clean_df`.

### Plot

The third cell makes:

- A scatter plot of `study_hours` vs `score`.
- A regression line fitted with `numpy.polyfit`.

### Evaluation check

The test condition is:

- `clean_df.isna().sum().sum() == 0`

If true, the student passes.

## How to build another exercise

Use this pattern:

1. Copy the migration style from `apps/exercises/migrations/0002_seed_missing_values_exercise.py`.
2. Change the slug, title, intro, and starter code.
3. Keep the notebook in 2-3 simple cells:
   - Generate or load data
   - Student action
   - Plot + check variable
4. Set `evaluation_rules` with:
   - `required_variables`
   - `assertions`
   - `success_message`
   - `failure_message`
5. Keep allowed libraries small and focused.
6. Add a test in `apps/exercises/tests.py` to prove it passes with a correct solution.

## Practical authoring tips

- Keep instructions short and direct.
- Make sure students only edit one clear cell.
- Give one clear success rule.
- Use deterministic generated data (`seed`) so students and teachers see consistent behavior.
- Include a visual so progress feels concrete.

## Quick checklist for new exercises

- [ ] Exercise has a unique slug.
- [ ] Intro clearly explains the student task.
- [ ] Starter code runs from top to bottom.
- [ ] Evaluation checks match the learning goal.
- [ ] Right-side plot appears after run.
- [ ] Reset Data returns the original exercise state.
- [ ] Test added and passing.
