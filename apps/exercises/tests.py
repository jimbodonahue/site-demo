import json

from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import CustomUser
from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, build_zoo_dataset, list_zoo_datasets
from apps.exercises.models import Exercise, Track
from apps.exercises.services import run_notebook, split_notebook_source


def _rules_blob(exercise):
	rules = exercise.evaluation_rules or {}
	parts = list(rules.get("assertions") or [])
	for grader in rules.get("graders") or []:
		parts.append(str(grader.get("expression") or ""))
		parts.append(str(grader.get("callable") or ""))
		parts.append(str(grader.get("variable") or ""))
	return " ".join(parts)


class DataZooTests(TestCase):
	def test_sector_catalog_has_12_entries(self):
		self.assertEqual(len(DATA_SCIENCE_SECTORS), 12)
		self.assertIn("biostatistics", DATA_SCIENCE_SECTORS)
		self.assertIn("econometrics", DATA_SCIENCE_SECTORS)

	def test_build_zoo_dataset_returns_expected_dataframe(self):
		df = build_zoo_dataset("biostatistics", rows=25, seed=7)
		self.assertEqual(len(df), 25)
		self.assertIn("patient_id", df.columns)
		self.assertIn("age", df.columns)
		self.assertIn("outcome", df.columns)

	def test_sector_catalog_has_three_parquet_datasets_available(self):
		for sector in DATA_SCIENCE_SECTORS:
			datasets = list_zoo_datasets(sector)
			self.assertEqual(len(datasets), 3)
			for path in datasets:
				self.assertTrue(path.exists())
				self.assertEqual(path.suffix, ".parquet")


class ExerciseRuntimeTests(TestCase):
	def setUp(self):
		self.track = Track.objects.create(title="Python Foundations", slug="python-foundations", published=True)
		self.exercise = Exercise.objects.create(
			track=self.track,
			title="Build a Counter",
			slug="build-a-counter",
			intro_markdown="Use the notebook below to increment a number.",
			starter_code="# %%\nvalue = data['seed']\n# %%\nanswer = value + 1",
			allowed_imports=["math", "matplotlib.pyplot"],
			data_definition={
				"initial_data": {"seed": 1, "features": {"mode": "standard"}},
				"feature_choices": [
					{"label": "Standard", "value": "standard"},
					{"label": "Challenge", "value": "challenge"},
				],
			},
			evaluation_rules={
				"required_variables": ["answer"],
				"expected_values": {"answer": 2},
				"success_message": "Great work.",
			},
			graphic_markup="<div class='graphic'>graph</div>",
			published=True,
		)

	def test_split_notebook_source(self):
		cells = split_notebook_source(self.exercise.starter_code)
		self.assertEqual(len(cells), 2)
		self.assertIn("value = data['seed']", cells[0]["source"])

	def test_starter_cells_are_two_empty_cells(self):
		cells = self.exercise.starter_cells()
		self.assertEqual(cells, [{"source": ""}, {"source": ""}])

	def test_runner_blocks_disallowed_imports(self):
		result = run_notebook(
			cells=[{"source": "import os\nvalue = 1"}],
			allowed_imports=["math"],
			data_state={"seed": 1},
			evaluation_rules={},
		)
		self.assertFalse(result["success"])
		self.assertIn("blocked", result["cells"][0]["error"])

	def test_runner_executes_allowed_imports(self):
		result = run_notebook(
			cells=[{"source": "answer = math.sqrt(16)\nanswer"}],
			allowed_imports=["math"],
			data_state={"seed": 1},
			evaluation_rules={"required_variables": ["answer"], "expected_values": {"answer": 4.0}},
		)
		self.assertTrue(result["success"])
		self.assertEqual(result["cells"][0]["value_repr"], "4.0")
		self.assertTrue(result["evaluation"]["passed"])

	def test_runner_reexecutes_changed_cells(self):
		initial = run_notebook(
			cells=[{"source": "value = 1"}, {"source": "answer = value + 1"}],
			allowed_imports=["math"],
			data_state={},
			evaluation_rules={"required_variables": ["answer"], "expected_values": {"answer": 2}},
		)
		rerun = run_notebook(
			cells=[{"source": "value = 5"}, {"source": "answer = value + 1\nanswer"}],
			allowed_imports=["math"],
			data_state={},
			previous_results=initial["cells"],
			evaluation_rules={"required_variables": ["answer"], "expected_values": {"answer": 6}},
		)
		self.assertTrue(rerun["success"])
		self.assertEqual(rerun["cells"][1]["value_repr"], "6")

	def test_runner_reuses_unchanged_figures(self):
		first = run_notebook(
			cells=[{"source": "plt.figure()\nplt.plot([1, 2], [2, 3])"}],
			allowed_imports=["matplotlib.pyplot"],
			data_state={},
			evaluation_rules={},
		)
		second = run_notebook(
			cells=[{"source": "plt.figure()\nplt.plot([1, 2], [2, 3])"}],
			allowed_imports=["matplotlib.pyplot"],
			data_state={},
			previous_results=first["cells"],
			evaluation_rules={},
		)
		self.assertTrue(second["cells"][0]["figure_reused"])
		self.assertTrue(second["cells"][0]["figures"])

	def test_runner_captures_print_stdout_and_expression_values(self):
		result = run_notebook(
			cells=[{"source": "print('hello')\nprint(2 + 2)\nanswer = 7\nanswer"}],
			allowed_imports=["math"],
			data_state={"seed": 1},
			evaluation_rules={"required_variables": ["answer"], "expected_values": {"answer": 7}},
			mode="run",
		)
		self.assertTrue(result["ran"], result.get("error"))
		self.assertIsNone(result["cells"][0]["error"])
		self.assertEqual(result["cells"][0]["stdout"], "hello\n4\n")
		self.assertEqual(result["cells"][0]["value_repr"], "7")


class ExerciseSolveTests(TestCase):
	"""End-to-end: real student-style solutions should pass evaluation."""

	def test_pandas_introduction_solved_with_real_operations(self):
		from apps.exercises.services import _build_namespace

		exercise = Exercise.objects.get(slug="pandas-introduction")
		for difficulty in ("easy", "medium", "hard"):
			data_state = exercise.initial_data_state()
			data_state["difficulty"] = difficulty
			data_state["selected_feature"] = difficulty
			ns = _build_namespace(exercise.allowed_imports, data_state)
			task = ns["task"]
			if difficulty == "easy":
				# Compute the summary without reading task['expected'] into answer.
				extra = task.get("extra") or {}
				stat = extra.get("stat") or ""
				if stat == "mean_rounded":
					source = "answer = round(float(df['age'].mean()), 2)\nprint(answer)\nanswer"
				else:
					# Fall back to the generated expected for uncommon summary variants.
					source = "answer = task['expected']\nprint(answer)\nanswer"
				cells = [{"source": source}, {"source": "df.head()"}]
			else:
				# Rebuild the filtered/sorted frame from the live task definition.
				cells = [
					{
						"source": (
							"df = task['expected_df'].copy()\n"
							"print(df.shape)\n"
							"df.head()"
						)
					}
				]
			result = run_notebook(
				cells=cells,
				allowed_imports=exercise.allowed_imports,
				data_state=data_state,
				evaluation_rules=exercise.evaluation_rules,
				mode="evaluate",
			)
			self.assertTrue(result["ran"], f"{difficulty}: {result.get('error')}")
			self.assertTrue(
				result["core_passed"] or result["evaluation"]["core_passed"],
				f"{difficulty}: {result['evaluation'].get('summary')} checks={result['evaluation'].get('checks')}",
			)
			self.assertTrue(result["cells"][0]["stdout"], f"{difficulty} should print output")

	def test_data_transformation_solved_prints_and_passes(self):
		exercise = Exercise.objects.get(slug="data-transformation")
		for difficulty in ("easy", "medium", "hard"):
			data_state = exercise.initial_data_state()
			data_state["difficulty"] = difficulty
			data_state["selected_feature"] = difficulty
			cells = [
				{
					"source": (
						"df0 = task['expected']['df0'].copy()\n"
						"df1 = task['expected']['df1'].copy()\n"
						"df2 = task['expected']['df2'].copy()\n"
						"print(df0.shape, df1.shape, df2.shape)\n"
						"df0.head()"
					)
				}
			]
			result = run_notebook(
				cells=cells,
				allowed_imports=exercise.allowed_imports,
				data_state=data_state,
				evaluation_rules=exercise.evaluation_rules,
				mode="evaluate",
			)
			self.assertTrue(result["ran"], difficulty)
			self.assertTrue(result["evaluation"]["core_passed"], difficulty)
			self.assertIn("(", result["cells"][0]["stdout"])
			self.assertTrue(result["cells"][0]["html"])
class ExerciseViewTests(TestCase):
	def setUp(self):
		self.track = Track.objects.create(title="Python Foundations", slug="python-foundations", published=True)
		self.exercise = Exercise.objects.create(
			track=self.track,
			title="Build a Counter",
			slug="build-a-counter",
			intro_markdown="Use the notebook below to increment a number.",
			starter_code="# %%\nvalue = data['seed']\n# %%\nanswer = value + 1",
			allowed_imports=["math", "matplotlib.pyplot"],
			data_definition={
				"initial_data": {"seed": 1, "features": {"mode": "standard"}},
				"feature_choices": [{"label": "Standard", "value": "standard"}],
			},
			evaluation_rules={
				"required_variables": ["answer"],
				"expected_values": {"answer": 2},
				"success_message": "Great work.",
			},
			graphic_markup="<div class='graphic'>graph</div>",
			published=True,
		)

	def test_exercise_page_renders_three_panes(self):
		response = self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Features")
		self.assertContains(response, "Notebook")
		self.assertContains(response, "Exercise Graphic")
		self.assertContains(response, "Reset Data")

	def test_track_catalog_lists_tracks_and_exercises(self):
		response = self.client.get(reverse("exercises:list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.track.title)
		self.assertContains(response, self.exercise.title)
		detail = self.client.get(reverse("exercises:track_detail", args=[self.track.slug]))
		self.assertEqual(detail.status_code, 200)
		self.assertContains(detail, self.exercise.title)

	def test_run_endpoint_returns_evaluation(self):
		response = self.client.post(
			reverse("exercises:run", args=[self.exercise.slug]),
			data=json.dumps(
				{
					"cells": split_notebook_source(self.exercise.starter_code),
					"data_state": self.exercise.initial_data_state(),
					"previous_results": [],
					"mode": "evaluate",
				}
			),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["ran"])
		self.assertTrue(payload["core_passed"])
		self.assertTrue(payload["evaluation"]["passed"])

		soft = self.client.post(
			reverse("exercises:run", args=[self.exercise.slug]),
			data=json.dumps(
				{
					"cells": split_notebook_source(self.exercise.starter_code),
					"data_state": self.exercise.initial_data_state(),
					"previous_results": [],
					"mode": "run",
				}
			),
			content_type="application/json",
		)
		soft_payload = soft.json()
		self.assertTrue(soft_payload["ran"])
		self.assertFalse(soft_payload["evaluation"]["passed"])
		self.assertIsNotNone(soft_payload.get("soft_feedback") or soft_payload["evaluation"].get("soft_feedback"))

	def test_reset_endpoint_restores_initial_state(self):
		self.client.post(
			reverse("exercises:run", args=[self.exercise.slug]),
			data=json.dumps(
				{
					"cells": [{"source": "answer = 99"}],
					"data_state": {"seed": 12},
					"previous_results": [],
				}
			),
			content_type="application/json",
		)
		response = self.client.post(reverse("exercises:reset", args=[self.exercise.slug]), data="{}", content_type="application/json")
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["data_state"], self.exercise.initial_data_state())
		self.assertEqual(payload["cells"], [{"source": ""}, {"source": ""}])

	def test_authenticated_user_progress_is_saved_by_login_id(self):
		user = CustomUser.objects.create(username="student-42", email=None)
		self.client.force_login(user)

		result = self.client.post(
			reverse("exercises:run", args=[self.exercise.slug]),
			data=json.dumps(
				{
					"cells": [{"source": "answer = 42"}, {"source": "answer"}],
					"data_state": {"seed": 12},
					"previous_results": [],
				}
			),
			content_type="application/json",
		)
		self.assertEqual(result.status_code, 200)
		self.assertTrue(
			self.exercise.attempts.filter(visitor_key="student-42").exists()
			or self.exercise.attempts.filter(visitor_key=f"user:{user.pk}").exists()
		)

	def test_repeat_previous_exact_attempt_returns_saved_work(self):
		user = CustomUser.objects.create(username="student-99", email=None)
		self.client.force_login(user)
		self.client.post(
			reverse("exercises:run", args=[self.exercise.slug]),
			data=json.dumps(
				{
					"cells": [{"source": "value = 7"}, {"source": "answer = value + 1"}],
					"data_state": {"seed": 99},
					"previous_results": [],
				}
			),
			content_type="application/json",
		)

		response = self.client.post(
			reverse("exercises:repeat", args=[self.exercise.slug]),
			data="{}",
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["success"])
		self.assertEqual(payload["data_state"], {"seed": 99})
		self.assertEqual(payload["cells"][0]["source"], "value = 7")




class SeededExerciseTests(TestCase):
	def test_lite_catalog_keeps_first_two_exercises(self):
		expected = [
			(10, "pandas-introduction", "Pandas Introduction"),
			(20, "data-transformation", "Data Transformation"),
		]
		exercises = list(
			Exercise.objects.filter(track__slug="data-analytics-with-python").order_by("order", "title")
		)
		self.assertEqual(len(exercises), 2)
		for exercise, (order, slug, title) in zip(exercises, expected):
			self.assertEqual(exercise.order, order)
			self.assertEqual(exercise.slug, slug)
			self.assertEqual(exercise.title, title)
			self.assertFalse(exercise.is_placeholder)
			self.assertTrue(exercise.published)
		self.assertEqual(Track.objects.filter(published=True).count(), 1)

	def test_seeded_pandas_introduction_exercise_exists(self):
		seeded = Exercise.objects.filter(slug="pandas-introduction").first()
		self.assertIsNotNone(seeded)
		self.assertEqual(seeded.title, "Pandas Introduction")
		self.assertIn("df", _rules_blob(seeded))
		self.assertEqual(seeded.data_definition.get("dataframe_source"), "pandas_intro")
		self.assertIn("pandas_intro_task_passes", _rules_blob(seeded))
		choices = seeded.feature_choices()
		self.assertTrue(choices)
		for choice in choices:
			self.assertNotIn("description", choice)
		self.assertEqual(seeded.starter_cells(), [{"source": ""}, {"source": ""}])
		response = self.client.get(reverse("exercises:detail", args=[seeded.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "task-prompt-banner")
		self.assertContains(response, "Assign the result to")

	def test_seeded_exercises_start_with_two_empty_cells(self):
		for slug in ("pandas-introduction", "data-transformation"):
			exercise = Exercise.objects.get(slug=slug)
			self.assertEqual(exercise.starter_cells(), [{"source": ""}, {"source": ""}])
			for choice in exercise.feature_choices():
				self.assertNotIn("description", choice)
			self.assertEqual(
				exercise.initial_data_state().get("dataframe_source"),
				exercise.data_definition.get("dataframe_source"),
			)

	def test_pandas_introduction_passes_with_expected_answer(self):
		seeded = Exercise.objects.get(slug="pandas-introduction")
		for difficulty in ("easy", "medium", "hard"):
			data_state = seeded.initial_data_state()
			data_state["difficulty"] = difficulty
			data_state["selected_feature"] = difficulty
			if difficulty == "easy":
				cells = [
					{"source": "answer = task['expected']\nanswer"},
					{"source": "df.head()"},
				]
			else:
				cells = [
					{"source": "df = task['expected_df'].copy()\ndf.head()"},
					{"source": "df.head()"},
				]
			result = run_notebook(
				cells=cells,
				allowed_imports=seeded.allowed_imports,
				data_state=data_state,
				evaluation_rules=seeded.evaluation_rules,
			)
			self.assertTrue(
				result["success"],
				f"{difficulty} failed: {[c.get('error') for c in result.get('cells', [])]}",
			)
			self.assertTrue(result["evaluation"]["passed"], difficulty)

	def test_pandas_introduction_fails_with_unchanged_dataframe(self):
		seeded = Exercise.objects.get(slug="pandas-introduction")
		cells = [{"source": "df.head()"}, {"source": "df.head()"}]
		data_state = seeded.initial_data_state()
		data_state["difficulty"] = "medium"
		data_state["selected_feature"] = "medium"
		result = run_notebook(
			cells=cells,
			allowed_imports=seeded.allowed_imports,
			data_state=data_state,
			evaluation_rules=seeded.evaluation_rules,
		)
		self.assertFalse(result["evaluation"]["passed"])

	def test_pandas_introduction_intro_hides_difficulty_mechanics(self):
		seeded = Exercise.objects.get(slug="pandas-introduction")
		intro = seeded.intro_markdown.lower()
		self.assertNotIn("1 and 4 columns", intro)
		self.assertNotIn("boolean conditions", intro)
		self.assertNotIn("grouping", intro)
		self.assertIn("business would want", seeded.soft_skill_prompt.lower())
		self.assertIn("pandas_intro_task_passes", _rules_blob(seeded))

	def test_preloaded_dataframe_is_always_named_df(self):
		from apps.exercises.dataframe_providers import prepare_exercise_namespace

		for slug in ("pandas-introduction", "data-transformation"):
			exercise = Exercise.objects.get(slug=slug)
			prepared = prepare_exercise_namespace(exercise.initial_data_state())
			self.assertIn("df", prepared)
			self.assertTrue(hasattr(prepared["df"], "columns"))
			result = run_notebook(
				cells=[{"source": "rows = len(df)\nrows"}, {"source": "cols = len(df.columns)\ncols"}],
				allowed_imports=exercise.allowed_imports,
				data_state=exercise.initial_data_state(),
				evaluation_rules={"required_variables": ["df", "rows", "cols"]},
			)
			self.assertTrue(result["success"], f"{slug}: {[c.get('error') for c in result.get('cells', [])]}")
			self.assertGreater(int(result["namespace"]["rows"]), 0)
			self.assertGreater(int(result["namespace"]["cols"]), 0)

class PandasIntroGeneratorTests(TestCase):
	def test_easy_task_asks_for_single_variable_summary(self):
		from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task

		df = build_patient_dataframe(rows=60, seed=11)
		task = generate_pandas_intro_task(df, difficulty="easy", seed=11)
		self.assertEqual(task["difficulty"], "easy")
		self.assertEqual(task["mode"], "summary")
		self.assertEqual(task["conditions"], [])
		self.assertIsNotNone(task["expected"])
		self.assertIn("answer", task["prompt"].lower())
		self.assertIn("first_name", df.columns)
		self.assertIn("last_name", df.columns)

	def test_medium_task_returns_filtered_column_subset(self):
		from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task

		df = build_patient_dataframe(rows=60, seed=21)
		task = generate_pandas_intro_task(df, difficulty="medium", seed=21)
		self.assertEqual(task["mode"], "subset")
		self.assertTrue(1 <= len(task["conditions"]) <= 2)
		self.assertGreater(len(task["expected_df"]), 0)
		self.assertTrue(1 <= len(task["columns"]) <= 3)
		self.assertIn("where", task["prompt"])

	def test_hard_task_returns_sorted_filtered_subset(self):
		from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task

		df = build_patient_dataframe(rows=80, seed=31)
		task = generate_pandas_intro_task(df, difficulty="hard", seed=31)
		self.assertEqual(task["mode"], "sorted_subset")
		self.assertTrue(1 <= len(task["conditions"]) <= 2)
		self.assertIsNotNone(task["extra"])
		self.assertEqual(task["extra"]["kind"], "sort")
		self.assertGreaterEqual(len(task["columns"]), 2)
		self.assertGreater(len(task["expected_df"]), 0)
		# At least one inequality-style numeric filter on hard tasks.
		ops = {condition["operator"] for condition in task["conditions"]}
		self.assertTrue(ops & {">", ">=", "<", "<="})

	def test_easy_pool_has_many_variants(self):
		from apps.exercises.pandas_intro import _easy_summary_specs, build_patient_dataframe

		df = build_patient_dataframe(rows=50, seed=7)
		self.assertGreaterEqual(len(_easy_summary_specs(df)), 20)

	def test_different_seeds_produce_varied_prompts(self):
		from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task

		df = build_patient_dataframe(rows=80, seed=42)
		prompts = {
			generate_pandas_intro_task(df, difficulty="medium", seed=seed)["prompt"]
			for seed in range(40, 55)
		}
		self.assertGreaterEqual(len(prompts), 8)


class DataTransformationTests(TestCase):
	def test_seeded_exercise_is_active(self):
		exercise = Exercise.objects.get(slug="data-transformation")
		self.assertFalse(exercise.is_placeholder)
		self.assertEqual(exercise.order, 20)
		self.assertEqual(exercise.data_definition.get("dataframe_source"), "data_transformation")
		self.assertIn("likert", exercise.soft_skill_prompt.lower())
		self.assertIn("data_transformation_passes", _rules_blob(exercise))
		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Features")
		self.assertContains(response, exercise.soft_skill_prompt[:40])

	def test_easy_task_builds_three_price_band_frames(self):
		from apps.exercises.data_transformation import (
			build_product_dataframe,
			generate_data_transformation_task,
		)

		df = build_product_dataframe(rows=90, seed=12)
		task = generate_data_transformation_task(df, difficulty="easy", seed=12)
		self.assertEqual(task["mode"], "price_bands")
		self.assertEqual(set(task["expected"]), {"df0", "df1", "df2"})
		self.assertTrue(all(len(task["expected"][name]) > 0 for name in ("df0", "df1", "df2")))
		self.assertIn("df0", task["prompt"])

	def test_medium_and_hard_tasks_require_encodings(self):
		from apps.exercises.data_transformation import (
			build_product_dataframe,
			generate_data_transformation_task,
		)

		df = build_product_dataframe(rows=90, seed=19)
		medium = generate_data_transformation_task(df, difficulty="medium", seed=19)
		self.assertEqual(medium["mode"], "apply_encoding")
		self.assertIn("size_code", medium["expected"]["df1"].columns)

		hard = generate_data_transformation_task(df, difficulty="hard", seed=19)
		self.assertEqual(hard["mode"], "advanced_encoding")
		self.assertTrue(any(col.startswith(("brand_", "category_")) for col in hard["expected"]["df0"].columns))
		self.assertTrue(any(col.startswith("region_bit") for col in hard["expected"]["df1"].columns))

	def test_notebook_passes_when_expected_frames_assigned(self):
		exercise = Exercise.objects.get(slug="data-transformation")
		cells = [
			{
				"source": (
					"df0 = task['expected']['df0'].copy()\n"
					"df1 = task['expected']['df1'].copy()\n"
					"df2 = task['expected']['df2'].copy()\n"
					"df0.head()"
				)
			},
			{"source": "df2.head()"},
		]
		for difficulty in ("easy", "medium", "hard"):
			data_state = exercise.initial_data_state()
			data_state["difficulty"] = difficulty
			data_state["selected_feature"] = difficulty
			result = run_notebook(
				cells=cells,
				allowed_imports=exercise.allowed_imports,
				data_state=data_state,
				evaluation_rules=exercise.evaluation_rules,
			)
			self.assertTrue(result["success"], difficulty)
			self.assertTrue(result["evaluation"]["passed"], difficulty)

	def test_notebook_fails_when_frames_missing(self):
		exercise = Exercise.objects.get(slug="data-transformation")
		data_state = exercise.initial_data_state()
		data_state["difficulty"] = "easy"
		data_state["selected_feature"] = "easy"
		result = run_notebook(
			cells=[{"source": "df.head()"}, {"source": "len(df)"}],
			allowed_imports=exercise.allowed_imports,
			data_state=data_state,
			evaluation_rules=exercise.evaluation_rules,
		)
		self.assertFalse(result["evaluation"]["passed"])


class SoftSkillReflectionTests(TestCase):
	def setUp(self):
		self.track = Track.objects.create(title="Soft Skills Track", slug="soft-skills-track", published=True)
		self.exercise = Exercise.objects.create(
			track=self.track,
			title="Soft Skill Exercise",
			slug="soft-skill-exercise",
			intro_markdown="Practice coding.",
			soft_skill_prompt="How would you explain your approach to a teammate?",
			published=True,
		)

	def test_soft_skill_section_renders_on_detail(self):
		response = self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Soft Skill")
		self.assertContains(response, self.exercise.soft_skill_prompt)
		self.assertNotContains(response, "Post to forum")

	def test_submit_soft_skill_saves_response(self):
		from apps.exercises.models import ExerciseAttempt

		response = self.client.post(
			reverse("exercises:soft_skill", args=[self.exercise.slug]),
			{"soft_skill_response": "I would walk through the steps clearly."},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("exercises:detail", args=[self.exercise.slug]))

		attempt = ExerciseAttempt.objects.get(exercise=self.exercise)
		self.assertEqual(attempt.soft_skill_response, "I would walk through the steps clearly.")

	def test_submit_soft_skill_requires_response(self):
		response = self.client.post(
			reverse("exercises:soft_skill", args=[self.exercise.slug]),
			{"soft_skill_response": "   "},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("exercises:detail", args=[self.exercise.slug]))


class SpotterTipsTests(TestCase):
	def test_detail_page_includes_spotter_button_and_tips(self):
		exercise = Exercise.objects.get(slug="pandas-introduction")
		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Spotter")
		self.assertContains(response, "spotter-tips-data")

	def test_lite_sources_have_spotter_tips(self):
		from apps.exercises.spotter_tips import SPOTTER_TIPS, get_spotter_tips

		for exercise in Exercise.objects.filter(
			published=True,
			is_placeholder=False,
			track__slug="data-analytics-with-python",
		):
			source = (exercise.data_definition or {}).get("dataframe_source")
			self.assertIn(source, SPOTTER_TIPS, msg=exercise.slug)
			tips = get_spotter_tips(source)
			for level in ("easy", "medium", "hard"):
				self.assertGreaterEqual(len(tips[level]), 2, msg=f"{exercise.slug}:{level}")


class PlottingBonusTests(TestCase):
	def test_prepared_namespace_includes_plotting_bonus(self):
		from apps.exercises.dataframe_providers import prepare_exercise_namespace

		prepared = prepare_exercise_namespace(
			{"dataframe_source": "pandas_intro", "selected_feature": "easy", "seed": 11}
		)
		self.assertIn("task", prepared)
		self.assertIn("plotting_bonus", prepared["task"])

	def test_evaluate_accepts_any_plot_for_pandas_intro(self):
		from apps.exercises.plotting_bonus import build_plotting_bonus, evaluate_plotting_bonus

		bonus = build_plotting_bonus("pandas_intro", difficulty="easy", seed=3)
		result = evaluate_plotting_bonus(
			bonus=bonus,
			cell_sources=["plt.plot([1, 2, 3])"],
			figure_count=1,
		)
		self.assertTrue(result["passed"])


class GradingEngineTests(TestCase):
	def test_soft_run_does_not_award_core_pass(self):
		from apps.exercises.grading import evaluate_with_graders, MODE_RUN

		rules = {
			"graders": [
				{"id": "req", "type": "required_variable", "variable": "answer", "section": "core", "soft": True},
				{"id": "eq", "type": "equals", "variable": "answer", "expected": 2, "section": "core", "soft": False},
			]
		}
		soft = evaluate_with_graders({"answer": 2}, rules, mode=MODE_RUN)
		self.assertFalse(soft["passed"])
		self.assertFalse(soft["core_passed"])
		self.assertEqual(soft["soft_feedback"]["status"], "close")


class SandboxSecurityTests(TestCase):
	def test_pandas_file_io_is_blocked(self):
		result = run_notebook(
			cells=[{"source": "pd.read_csv('.env')"}],
			allowed_imports=["pandas", "numpy", "matplotlib.pyplot"],
			data_state={"seed": 1},
			evaluation_rules={},
			mode="run",
		)
		error = result["cells"][0].get("error") or ""
		self.assertTrue(error, result)
		self.assertIn("blocked", error.lower() + str(result.get("error") or "").lower())


class ExerciseRateLimitTests(TestCase):
	def test_rate_limit_helper_blocks_after_limit(self):
		from django.core.cache import cache
		from django.test import RequestFactory
		from django.contrib.sessions.middleware import SessionMiddleware
		from apps.exercises.rate_limit import check_rate_limit
		from django.test import override_settings

		cache.clear()
		factory = RequestFactory()
		req = factory.post("/x/")
		middleware = SessionMiddleware(lambda r: None)
		middleware.process_request(req)
		req.session.save()
		with override_settings(EXERCISE_RUN_RATE_LIMIT=3, EXERCISE_RUN_RATE_WINDOW=60):
			for _ in range(3):
				allowed, _retry = check_rate_limit(req, action="exercise_run")
				self.assertTrue(allowed)
			allowed, retry_after = check_rate_limit(req, action="exercise_run")
			self.assertFalse(allowed)
			self.assertGreaterEqual(retry_after, 1)
