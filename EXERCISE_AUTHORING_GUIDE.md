# Exercise Authoring Guide

This guide explains how to create and maintain programming exercises for the learning platform.

## What an exercise is

An exercise is a structured programming activity with three parts:

1. An intro that explains the goal and setup.
2. A coding workspace where the student writes and runs Python.
3. An evaluation section that explains how the platform checks progress and correctness.

Each exercise should also have:

- A left-side panel for choosing data features or scenario options.
- A right-side panel with an exercise-specific graphic and a visible progress summary.
- A reset action so students can restore the original data state and try again.

## Content model

Use the `apps/exercises` app to store exercise content and runtime metadata. Each exercise should be linked to a course or lesson in `apps/courses`.

Recommended fields:

- `title`: The exercise title shown to students.
- `slug`: A stable URL-friendly identifier.
- `intro`: Short text that introduces the task.
- `starter_code`: The initial notebook code shown to the student.
- `allowed_imports`: The libraries the student can import.
- `data_definition`: The original dataset or data configuration for the attempt.
- `evaluation_rules`: The checks used to determine success.
- `published`: Whether the exercise is visible to students.
- `order`: Display order within a course or module.
- `linked_course` or `linked_lesson`: The parent content item.

## Exercise structure

A good exercise usually follows this flow:

1. Explain the goal in plain language.
2. Show the data features or options the student can choose.
3. Present the coding space.
4. Provide a visible result area with a graphic or summary.
5. Explain how progress is measured.
6. Offer a Reset Data button.

The coding area should behave like a notebook:

- Cells can be added and edited.
- Running a cell shows output below it.
- Changing a cell reruns that cell and the cells after it.
- Figures should only rerender when the figure-producing cell changes.

## Allowed libraries

Exercises should preload the libraries students are allowed to use.

Typical first-version allowlist:

- `python` built-ins
- `numpy`
- `pandas`
- `matplotlib`

Do not rely on students importing arbitrary packages. The runtime should reject disallowed imports before execution. If a student tries to use an unsupported package, the interface should show a clear, friendly error explaining that the import is blocked.

## Data handling

Each exercise should have a clean starting state.

Authoring requirements:

- Store the original data separately from any student changes.
- Define exactly what state is reset when the student clicks Reset Data.
- Preserve the code the student has written unless the exercise explicitly says otherwise.
- Make the initial data deterministic so the exercise behaves the same every time.

If an exercise uses generated data, the generation should be seeded and the seed should be stored with the exercise definition.

## Evaluation rules

Evaluation should combine human guidance and machine checks.

Use human-readable text for:

- What the student is expected to learn.
- What the final result should look like.
- Common mistakes and hints.

Use machine-checkable rules for:

- Whether the expected variables exist.
- Whether output values match a target result.
- Whether data transformations were performed correctly.
- Whether required plots or figures were produced.

Prefer evaluation rules that are easy to understand and easy to test. Avoid hidden grading logic that the student cannot inspect.

## Figure and visualization behavior

If an exercise includes visuals:

- Define which cell or output produces the visual.
- Cache figure output until the producing cell changes.
- Show a placeholder if the visual has not been generated yet.
- Include alt text or a short description for accessibility.

## Progress tracking

Progress should be visible to the student.

Track items such as:

- Whether the intro has been opened.
- Which cells have been run.
- Whether the expected data state has been reached.
- Whether evaluation criteria are satisfied.
- Whether the exercise has been reset.

Use progress tracking to show a clear completion status without exposing implementation details the student does not need.

## Authoring checklist

Before publishing an exercise, confirm:

- The intro is clear and concise.
- The starter code runs without errors.
- The allowed imports are restricted to the intended libraries.
- The reset behavior restores the original data.
- The evaluation rules match the intended learning outcome.
- The notebook workspace reruns correctly after edits.
- The right-side graphic and progress panel render properly.
- The exercise is linked to the correct course or lesson.

## Writing style

Write exercises for non-technical readers as well as technical students:

- Use short paragraphs.
- Prefer direct instructions.
- Explain why a step matters when it is not obvious.
- Avoid jargon unless the exercise is specifically teaching that concept.
- Provide one clear objective per exercise whenever possible.

## Suggested author workflow

1. Create the exercise record in the admin.
2. Add the intro, starter code, and allowed imports.
3. Define the starting data and reset behavior.
4. Add the evaluation rules.
5. Upload or configure the exercise graphic.
6. Test the notebook flow from edit to rerun to reset.
7. Publish the exercise only after the checks pass.

## Future extensions

Later versions of the platform may add:

- More advanced sandboxing for code execution.
- Per-cell hints and automatic feedback.
- A richer figure caching system.
- More granular progress analytics.
- Importing exercise content from Markdown files in the repository.

## Summary

A strong exercise is clear, deterministic, and resettable. It should guide the student through a small programming task, let them experiment safely, and give them feedback that connects directly to the learning goal.