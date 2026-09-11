## Plan: Notebook-Style Exercises

Build exercises as the main interactive learning surface. Each exercise should present an intro, a notebook-like coding area, and an evaluation panel, with a left column for data-feature choices and a right column for an exercise graphic plus progress. Because the repo currently has no execution stack, the plan should add a dedicated runtime layer instead of trying to run Python inside normal Django views.

**Steps**

1. Define the exercise domain in [apps/exercises/models.py](/home/jim/django-platform/apps/exercises/models.py). Model the exercise itself, its intro, starter code, allowed imports, data configuration, evaluation rules, progress state, and attempt history. Link each exercise back to a course or lesson in [apps/courses/models.py](/home/jim/django-platform/apps/courses/models.py).

2. Design the page as a three-pane workspace. The left pane controls data features and exercise configuration, the center pane is the notebook-like coding workspace, and the right pane shows an exercise-specific graphic above and progress/status below. Keep the intro and evaluation visible so the page feels like a guided lab, not a generic editor.

3. Define a notebook execution contract. Represent cells, outputs, and dependencies so the app can rerun downstream cells when one changes. The rule should be: rerun from the changed cell onward, and only regenerate figures when the figure-producing cell changes.

4. Choose and isolate the runtime. The safest first version is a sandboxed browser worker or iframe-based runtime with a strict message protocol for running cells, returning output, and reporting blocked imports or reset events. If a backend sandbox is chosen later, the same model and UI contract can still work.

5. Enforce import restrictions and preloaded libraries. Preload the approved libraries in the sandbox, block disallowed imports before execution, and show a clear error when the student tries to use an unsupported library. The restriction needs to be enforced outside the normal Django request lifecycle.

6. Add resettable data state. Store the original data snapshot separately from the student’s mutable state, and wire a top-level Reset Data button that restores the canonical starting data, outputs, and progress markers for the attempt.

7. Build evaluation as structured logic, not just prose. Keep human-readable evaluation text, but also define machine-checkable assertions so the platform can validate notebook output, transformed data, or final state after execution.

8. Add the view and template layer for the exercise shell. Use [apps/exercises/views.py](/home/jim/django-platform/apps/exercises/views.py), app-local URLs, and exercise-specific templates under [templates/](/home/jim/django-platform/templates) to render the notebook workspace. Reuse the existing page chrome in [templates/base.html](/home/jim/django-platform/templates/base.html) for the outer layout.

9. Add tests around the execution behavior. Cover model relationships, import blocking, notebook rerun behavior, figure caching, data reset behavior, and evaluation outcomes. Add at least one end-to-end test for the exercise shell layout so the three-pane structure stays intact.

10. Update [CHANGELOG.md](/home/jim/django-platform/CHANGELOG.md) to refelct these changes.

**Relevant files**

- [apps/exercises/models.py](/home/jim/django-platform/apps/exercises/models.py) - exercise definitions, state, and evaluation metadata.
- [apps/exercises/views.py](/home/jim/django-platform/apps/exercises/views.py) - exercise shell and any run/reset endpoints.
- [apps/exercises/admin.py](/home/jim/django-platform/apps/exercises/admin.py) - authoring workflow for exercises and allowed libraries.
- [apps/exercises/tests.py](/home/jim/django-platform/apps/exercises/tests.py) - behavior tests for execution and reset rules.
- [apps/courses/models.py](/home/jim/django-platform/apps/courses/models.py) - course-to-exercise linkage.
- [templates/base.html](/home/jim/django-platform/templates/base.html) - global shell and extension points.
- [templates/](/home/jim/django-platform/templates) - exercise-specific UI templates.
- [project_core/urls.py](/home/jim/django-platform/project_core/urls.py) - route the exercises app.
- [project_core/settings.py](/home/jim/django-platform/project_core/settings.py) - app install and any sandbox policy settings.
- [Dockerfile](/home/jim/django-platform/Dockerfile) and [docker-compose.yml](/home/jim/django-platform/docker-compose.yml) - runtime boundary if execution moves into a sandbox service.

**Verification**

1. Confirm the exercise page renders the intro, notebook workspace, left data panel, and right progress/graphic panel.
2. Verify blocked imports fail before execution and allowed libraries are available by default.
3. Test rerun semantics by changing a middle cell and confirming downstream cells rerun while unchanged figure outputs stay cached.
4. Test Reset Data to ensure the original dataset and attempt state are restored.
5. Add evaluation tests that verify student output or transformed data against the exercise rules.
6. Run Django checks and targeted `apps.exercises` tests after the model and runtime contract are in place.

**Decisions**

- Make `apps/exercises` the primary interactive learning app.
- Keep course content and exercise execution separate, with exercises linked back to lessons.
- Prefer a sandboxed runtime contract over direct Python execution inside Django request handlers.
- Treat figures as cached artifacts that only regenerate when the producing cell changes.
- Use the browser as the first integration point unless you explicitly want a backend sandbox from day one.

**Further Considerations**

1. Do you want the runtime plan to assume browser-worker execution first, or should it be written around a separate backend sandbox service?
2. Which libraries should be pre-imported in the first version: core Python only, or core Python plus numpy/pandas/matplotlib?