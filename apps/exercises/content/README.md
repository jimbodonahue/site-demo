# Exercise content

Learner-facing copy lives here so it can be edited without hunting through
Python modules or migrations.

## Layout

```
content/
  exercises/<slug>/
    intro.md              # exercise intro (markdown)
    soft_skill.md         # reflection prompt
    graphic_markup.html   # optional panel HTML
    starter.py            # optional starter notebook source
    messages.json         # success/failure + grader next_action copy
  prompts/
    <module>.json         # dynamic task prompt templates ({placeholders})
  spotter_tips.json       # Spotter panel snippets by dataframe_source
  plotting.json           # plotting-bonus labels and prompt body
```

## Editing workflow

1. Change the relevant file under `content/`.
2. Dynamic prompts (`prompts/`, `spotter_tips.json`, `plotting.json`) apply on the next request.
3. Intro / soft skill / graphic / starter / messages also resolve at runtime via
   `Exercise.display_*` helpers. To keep the database in sync (admin, tests,
   anything reading fields directly), run:

```bash
.venv/bin/python manage.py sync_exercise_content
```
