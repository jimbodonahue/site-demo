import json

from django.test import TestCase
from django.urls import reverse

from apps.authentication.models import CustomUser
from apps.exercises.data_zoo import (
	DATA_SCIENCE_SECTORS,
	build_zoo_dataset,
	build_zoo_explore_notebook,
	list_zoo_datasets,
	topic_dataset_summaries,
)
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
	def test_sector_catalog_has_20_entries(self):
		self.assertEqual(len(DATA_SCIENCE_SECTORS), 20)
		self.assertIn("healthcare", DATA_SCIENCE_SECTORS)
		self.assertIn("finance", DATA_SCIENCE_SECTORS)
		self.assertIn("crime", DATA_SCIENCE_SECTORS)

	def test_build_zoo_dataset_returns_expected_dataframe(self):
		df = build_zoo_dataset("healthcare", rows=25, seed=7)
		self.assertEqual(len(df), 25)
		self.assertIn("patient_id", df.columns)
		self.assertIn("admission_age", df.columns)
		self.assertIn("discharge_status", df.columns)

	def test_sector_catalog_has_parquet_datasets_available(self):
		for sector in DATA_SCIENCE_SECTORS:
			datasets = list_zoo_datasets(sector)
			self.assertGreaterEqual(len(datasets), 1, sector)
			for path in datasets:
				self.assertTrue(path.exists())
				self.assertEqual(path.suffix, ".parquet")

	def test_refresh_scenario_always_changes_seed_and_maybe_topic(self):
		import numpy as np

		from apps.exercises.data_zoo import refresh_scenario_state

		base = {
			"dataframe_source": "pandas_intro",
			"data_field": "insurance",
			"topic": "insurance",
			"seed": 42,
			"dataset_file": "01_medical_cost_personal_dataset.parquet",
		}
		# Force topic change
		changed = refresh_scenario_state(
			base,
			change_topic_probability=1.0,
			rng=np.random.default_rng(0),
		)
		self.assertNotEqual(changed["seed"], 42)
		self.assertNotEqual(changed["data_field"], "insurance")
		self.assertEqual(changed["data_field"], changed["topic"])
		self.assertTrue(changed.get("dataset_file"))

		# Force keep topic
		kept = refresh_scenario_state(
			base,
			force_topic="retail",
			change_topic_probability=1.0,
			rng=np.random.default_rng(1),
		)
		self.assertEqual(kept["data_field"], "retail")
		self.assertNotEqual(kept["seed"], 42)

	def test_topic_dataset_summaries_include_stats(self):
		items = topic_dataset_summaries("healthcare", sample_rows=200)
		self.assertGreaterEqual(len(items), 1)
		first = items[0]
		self.assertTrue(first["ok"], first.get("error"))
		self.assertGreater(first["summary"]["full_rows"], 0)
		self.assertIn("numeric_summary", first["summary"])

	def test_data_zoo_page_renders(self):
		response = self.client.get(reverse("exercises:zoo"), {"topic": "healthcare"})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Zoo")
		self.assertContains(response, "Summary statistics")
		self.assertContains(response, "Explore with Python")
		self.assertEqual(response.context["selected_topic"], "healthcare")
		self.assertTrue(response.context["datasets"])

	def test_zoo_catalog_endpoint(self):
		response = self.client.get(reverse("exercises:zoo_catalog"), {"topic": "finance"})
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["success"])
		self.assertEqual(payload["topic"], "finance")
		self.assertGreaterEqual(len(payload["datasets"]), 1)

	def test_zoo_explore_run_loads_df(self):
		datasets = list_zoo_datasets("healthcare")
		self.assertTrue(datasets)
		cells = build_zoo_explore_notebook()
		cells[1]["source"] = "print(len(df), df.shape[1])\nlen(df)"
		response = self.client.post(
			reverse("exercises:zoo_run"),
			data=json.dumps(
				{
					"topic": "healthcare",
					"dataset_file": datasets[0].name,
					"cells": cells,
					"n_rows": 120,
					"seed": 3,
				}
			),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload.get("ran"), payload.get("error"))
		self.assertIn("120", (payload.get("cells") or [{}])[1].get("stdout") or "")


class ZooTopicPreferenceTests(TestCase):
	def setUp(self):
		from apps.authentication.models import UserProfile

		self.user = CustomUser.objects.create_user(
			email="zoofan@example.com",
			username="zoofan",
			password="pass12345",
		)
		UserProfile.objects.create(
			user=self.user,
			nickname="ZooFan",
			data_field="sports",
			preferred_topics=["sports", "finance", "retail"],
			dataset_file="",
		)
		self.exercise = Exercise.objects.get(slug="pandas-introduction")

	def test_new_attempt_defaults_to_profile_topic(self):
		self.client.force_login(self.user)
		response = self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		self.assertEqual(response.status_code, 200)
		data_state = response.context["initial_data"]
		self.assertEqual(data_state.get("data_field"), "sports")
		self.assertEqual(self.user.profile.primary_topic(), "sports")
		self.assertEqual(self.user.profile.ranked_topics()[0], "sports")
		self.assertEqual(len(self.user.profile.ranked_topics()), 3)

	def test_reset_refreshes_seed_and_returns_new_dataset(self):
		self.client.force_login(self.user)
		# Prime an attempt
		self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		first = self.client.post(
			reverse("exercises:reset", args=[self.exercise.slug]),
			data=json.dumps({"difficulty": "easy"}),
			content_type="application/json",
		)
		self.assertEqual(first.status_code, 200)
		first_payload = first.json()
		self.assertTrue(first_payload["success"])
		first_seed = first_payload["data_state"]["seed"]

		second = self.client.post(
			reverse("exercises:reset", args=[self.exercise.slug]),
			data=json.dumps({"difficulty": "easy"}),
			content_type="application/json",
		)
		self.assertEqual(second.status_code, 200)
		second_payload = second.json()
		self.assertNotEqual(second_payload["data_state"]["seed"], first_seed)
		page = self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		self.assertContains(page, "Click again to refresh data")
		self.assertContains(page, "Clicking the current difficulty refreshes")

	def test_locked_topic_refresh_keeps_selected_topic(self):
		self.client.force_login(self.user)
		self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		response = self.client.post(
			reverse("exercises:reset", args=[self.exercise.slug]),
			data=json.dumps(
				{
					"data_field": "finance",
					"topic": "finance",
					"lock_topic": True,
					"difficulty": "medium",
				}
			),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertEqual(payload["data_state"]["data_field"], "finance")
		self.assertEqual(payload["data_state"]["difficulty"], "medium")


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

	def test_starter_cells_omit_imports_and_include_plotting_bonus(self):
		cells = self.exercise.starter_cells(plotting_bonus_prompt="### Plotting bonus")
		self.assertGreaterEqual(len(cells), 3)
		self.assertTrue(all(cell.get("role") != "imports" for cell in cells))
		self.assertEqual(cells[0]["role"], "work")
		self.assertEqual(cells[-2]["cell_type"], "markdown")
		self.assertIn("Plotting bonus", cells[-2]["source"])
		self.assertTrue(cells[-1]["source"].startswith("import matplotlib.pyplot as plt"))

	def test_runner_blocks_disallowed_imports(self):
		result = run_notebook(
			cells=[{"source": "import os\nvalue = 1"}],
			allowed_imports=["math"],
			data_state={"seed": 1},
			evaluation_rules={},
		)
		self.assertFalse(result["success"])
		self.assertIn("not allowed", result["cells"][0]["error"])

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
		self.placeholder = Exercise.objects.create(
			track=self.track,
			title="Future Exercise",
			slug="future-exercise",
			order=99,
			is_placeholder=True,
			published=True,
		)

	def test_exercise_page_renders_three_panes(self):
		response = self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Features")
		self.assertContains(response, "Notebook")
		self.assertContains(response, "Visual Reference & Data Preview")
		self.assertNotContains(response, "Exercise Graphic")
		self.assertNotContains(response, "tb-restart")
		self.assertContains(response, "New Exercise")
		self.assertContains(response, "Code ran successfully")

	def test_exercise_page_links_to_adjacent_track_topics(self):
		next_exercise = Exercise.objects.create(
			track=self.track,
			title="Middle Exercise",
			slug="middle-exercise",
			order=50,
			intro_markdown="Keep going.",
			starter_code="# %%\nanswer = 1",
			published=True,
		)
		first = self.client.get(reverse("exercises:detail", args=[self.exercise.slug]))
		self.assertContains(first, "Next Topic")
		self.assertContains(first, next_exercise.title)
		self.assertContains(first, reverse("exercises:detail", args=[next_exercise.slug]))
		self.assertNotContains(first, "Previous Topic")

		middle = self.client.get(reverse("exercises:detail", args=[next_exercise.slug]))
		self.assertContains(middle, "Previous Topic")
		self.assertContains(middle, self.exercise.title)
		self.assertContains(middle, "Next Topic")
		self.assertContains(middle, self.placeholder.title)

		last = self.client.get(reverse("exercises:detail", args=[self.placeholder.slug]))
		self.assertContains(last, "Previous Topic")
		self.assertContains(last, next_exercise.title)
		self.assertNotContains(last, "Next Topic")

	def test_track_catalog_lists_tracks_and_exercises(self):
		response = self.client.get(reverse("exercises:list"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, self.track.title)
		self.assertContains(response, self.exercise.title)
		# Placeholder exercises are listed but not linkable.
		self.assertContains(response, self.placeholder.title)
		self.assertContains(response, "Coming soon")
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

		run_only = self.client.post(
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
		run_payload = run_only.json()
		self.assertTrue(run_payload["ran"])
		self.assertFalse(run_payload["evaluation"]["passed"])
		self.assertFalse(run_payload["core_passed"])
		self.assertEqual(run_payload["evaluation"].get("checks"), [])
		self.assertIsNone(run_payload.get("soft_feedback"))
		self.assertIsNone(run_payload["evaluation"].get("soft_feedback"))
		self.assertIn("Evaluate Exercise", run_payload["progress"]["summary"])

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
		self.assertEqual(
			payload["cells"],
			self.exercise.starter_cells(plotting_bonus_prompt="### Plotting bonus"),
		)

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
		run = self.client.post(
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
		self.assertEqual(run.status_code, 200)
		self.assertEqual(run.json()["previous_attempts"][0]["try_number"], 1)

		listed = self.client.post(
			reverse("exercises:repeat", args=[self.exercise.slug]),
			data="{}",
			content_type="application/json",
		)
		self.assertEqual(listed.status_code, 200)
		list_payload = listed.json()
		self.assertTrue(list_payload["success"])
		self.assertEqual(list_payload["attempts"][0]["try_number"], 1)
		self.assertNotIn("seed", list_payload["attempts"][0])
		self.assertNotIn("data_state", list_payload)

		response = self.client.post(
			reverse("exercises:repeat", args=[self.exercise.slug]),
			data=json.dumps({"try_number": 1, "restore": True}),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["success"])
		self.assertEqual(payload["data_state"], {"seed": 99})
		self.assertEqual(payload["cells"][0]["source"], "value = 7")


class SeededExerciseTests(TestCase):
	fixtures = []

	def test_seeded_missing_values_exercise_exists(self):
		seeded = Exercise.objects.filter(slug="clean-messy-dataset").first()
		self.assertIsNotNone(seeded)
		self.assertEqual(seeded.title, "Data Cleaning: Missing Values")
		self.assertFalse(seeded.is_placeholder)
		self.assertEqual(seeded.order, 40)
		self.assertIn("df", _rules_blob(seeded))
		self.assertIn("missing_values_imputation_passes", _rules_blob(seeded))
		self.assertEqual(seeded.data_definition.get("dataframe_source"), "data_quality")
		choices = {choice["value"] for choice in seeded.feature_choices()}
		self.assertEqual(choices, {"easy", "medium", "hard"})
		self.assertFalse(Exercise.objects.filter(slug="fill-missing-values-generated-data").exists())

	def test_analytics_track_catalog_order_and_placeholders(self):
		expected = [
			(10, "pandas-introduction", "Pandas Introduction", False),
			(20, "data-transformation", "Data Transformation", False),
			(30, "data-cleaning-messy-dataset", "Data Cleaning: Messy Dataset", False),
			(40, "clean-messy-dataset", "Data Cleaning: Missing Values", False),
			(50, "descriptive-statistics", "Descriptive Statistics", False),
			(60, "ab-testing-conditional-probability", "A/B Testing and Conditional Probability", False),
		]
		exercises = list(
			Exercise.objects.filter(track__slug="data-analytics-with-python").order_by("order", "title")
		)
		self.assertEqual(len(exercises), 6)
		for exercise, (order, slug, title, placeholder) in zip(exercises, expected):
			self.assertEqual(exercise.order, order)
			self.assertEqual(exercise.slug, slug)
			self.assertEqual(exercise.title, title)
			self.assertEqual(exercise.is_placeholder, placeholder)
			self.assertTrue(exercise.published)

		response = self.client.get(reverse("exercises:detail", args=["data-transformation"]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Transformation")
		self.assertNotContains(response, "Coming soon")

		messy = self.client.get(reverse("exercises:detail", args=["data-cleaning-messy-dataset"]))
		self.assertEqual(messy.status_code, 200)
		self.assertContains(messy, "Data Cleaning: Messy Dataset")
		self.assertNotContains(messy, "Coming soon")

		ab_testing = self.client.get(reverse("exercises:detail", args=["ab-testing-conditional-probability"]))
		self.assertEqual(ab_testing.status_code, 200)
		self.assertContains(ab_testing, "A/B Testing")
		self.assertNotContains(ab_testing, "Coming soon")

		descriptive = self.client.get(reverse("exercises:detail", args=["descriptive-statistics"]))
		self.assertEqual(descriptive.status_code, 200)
		self.assertContains(descriptive, "Descriptive Statistics")
		self.assertNotContains(descriptive, "Coming soon")

	def test_seeded_exercise_run_passes_after_fill(self):
		seeded = Exercise.objects.get(slug="clean-messy-dataset")
		data_state = seeded.initial_data_state()
		data_state["data_field"] = "marketing"
		data_state["topic"] = "marketing"
		data_state["difficulty"] = "easy"
		data_state["selected_feature"] = "easy"
		cells = [
			{
				"source": (
					"df[target] = df[target].fillna(df[target].median())\n"
					"df.head()"
				)
			},
			{"source": "df.head()"},
		]

		result = run_notebook(
			cells=cells,
			allowed_imports=seeded.allowed_imports,
			data_state=data_state,
			evaluation_rules=seeded.evaluation_rules,
		)

		self.assertTrue(result["success"], f"Cell errors: {[c.get('error') for c in result.get('cells', [])]}")
		self.assertTrue(result["evaluation"]["passed"])
		self.assertIn("df", result["namespace"])
		self.assertIn("target", result["data_state"])
		self.assertIn("outcome", result["data_state"])
		self.assertIn("reference_plot", result["data_state"])

	def test_exercise_page_contains_live_plot_mount(self):
		seeded = Exercise.objects.get(slug="clean-messy-dataset")
		response = self.client.get(reverse("exercises:detail", args=[seeded.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "right-panel-live-plot")
		self.assertNotContains(response, "Starter data state")
		# Missing-values exercise ships a reference scatter plot, not a head() fallback.
		self.assertIn("reference_plot", response.context["initial_data"])
		self.assertNotIn("dataset_preview_html", response.context["initial_data"])

	def test_exercises_without_graphs_get_dataset_head_preview(self):
		from apps.exercises.dataframe_providers import enrich_data_state_visuals

		for slug in (
			"pandas-introduction",
			"data-transformation",
			"data-cleaning-messy-dataset",
			"descriptive-statistics",
			"ab-testing-conditional-probability",
		):
			exercise = Exercise.objects.get(slug=slug)
			enriched = enrich_data_state_visuals(exercise.initial_data_state())
			self.assertIn("dataset_preview_html", enriched, slug)
			self.assertIn("dataframe-preview", enriched["dataset_preview_html"], slug)
			self.assertNotIn("reference_plot", enriched, slug)
			response = self.client.get(reverse("exercises:detail", args=[slug]))
			self.assertEqual(response.status_code, 200, slug)
			self.assertIn("dataset_preview_html", response.context["initial_data"], slug)

	def test_seeded_pandas_introduction_exercise_exists(self):
		seeded = Exercise.objects.filter(slug="pandas-introduction").first()
		self.assertIsNotNone(seeded)
		self.assertEqual(seeded.title, "Pandas Introduction")
		self.assertIn("df", _rules_blob(seeded))
		self.assertEqual(seeded.data_definition.get("dataframe_source"), "pandas_intro")
		choices = seeded.feature_choices()
		self.assertTrue(choices)
		for choice in choices:
			self.assertNotIn("description", choice)
		starter = seeded.starter_cells()
		self.assertTrue(all(cell.get("role") != "imports" for cell in starter))
		self.assertEqual(starter[0]["role"], "work")
		self.assertEqual(starter[-1]["role"], "plotting_bonus")
		response = self.client.get(reverse("exercises:detail", args=[seeded.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "task-prompt-banner")
		self.assertContains(response, "Assign the result to")
		self.assertContains(response, "Preloaded libraries")
		self.assertContains(response, "numpy")
		self.assertContains(response, "pandas")


	def test_seeded_exercises_start_with_work_and_plotting_cells(self):
		for slug in (
			"clean-messy-dataset",
			"pandas-introduction",
		):
			exercise = Exercise.objects.get(slug=slug)
			starter = exercise.starter_cells(plotting_bonus_prompt="### Plotting bonus")
			self.assertTrue(all(cell.get("role") != "imports" for cell in starter))
			self.assertEqual(starter[0]["role"], "work")
			self.assertFalse(starter[0]["locked"])
			self.assertEqual(starter[-2]["role"], "plotting_bonus_prompt")
			self.assertEqual(starter[-1]["role"], "plotting_bonus")
			for choice in exercise.feature_choices():
				self.assertNotIn("description", choice)
			self.assertEqual(
				exercise.initial_data_state().get("dataframe_source"),
				exercise.data_definition.get("dataframe_source"),
			)

	def test_data_cleaning_exercise_renamed_and_has_topics(self):
		exercise = Exercise.objects.get(slug="clean-messy-dataset")
		self.assertEqual(exercise.title, "Data Cleaning: Missing Values")
		topics = {choice["value"] for choice in exercise.topic_choices()}
		self.assertIn("healthcare", topics)
		self.assertIn("marketing", topics)
		self.assertIn("missing_values_imputation_passes", _rules_blob(exercise))
		# Difficulty mechanics must stay hidden from learners.
		self.assertNotIn("20", exercise.intro_markdown)
		self.assertNotIn("median", exercise.intro_markdown.lower())

		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Zoo topic")
		self.assertContains(response, "Data Cleaning: Missing Values")
		self.assertContains(response, "Click again to refresh data")

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
		self.assertIn("business use case", seeded.soft_skill_prompt.lower())
		self.assertIn("pandas_intro_task_passes", _rules_blob(seeded))

	def test_preloaded_dataframe_is_always_named_df(self):
		from apps.exercises.dataframe_providers import prepare_exercise_namespace

		for slug in (
			"clean-messy-dataset",
			"pandas-introduction",
			"data-transformation",
			"data-cleaning-messy-dataset",
			"ab-testing-conditional-probability",
		):
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


class MissingValuesExerciseTests(TestCase):
	def setUp(self):
		from apps.exercises.missing_values import CACHE_DIR
		import shutil

		if CACHE_DIR.exists():
			shutil.rmtree(CACHE_DIR)

	def test_prepare_injects_missing_values_and_caches_baseline(self):
		from apps.exercises.missing_values import CACHE_DIR, prepare_missing_values_exercise

		prepared = prepare_missing_values_exercise(
			{
				"data_field": "healthcare",
				"dataset_file": "01_heart_disease_cleveland.parquet",
				"difficulty": "easy",
				"seed": 7,
			}
		)
		self.assertIn("df", prepared)
		self.assertIn("df_baseline", prepared)
		self.assertTrue(prepared["df"].isna().sum().sum() > 0)
		self.assertEqual(prepared["df"].isna().sum().sum(), prepared["df"][prepared["target"]].isna().sum())
		self.assertTrue(list(CACHE_DIR.glob("*.parquet")))
		self.assertEqual(prepared["df"].equals(prepared["df_baseline"]), True)

	def test_medium_and_hard_also_create_missingness(self):
		from apps.exercises.missing_values import prepare_missing_values_exercise

		for difficulty in ("medium", "hard"):
			prepared = prepare_missing_values_exercise(
				{
					"data_field": "healthcare",
					"dataset_file": "01_heart_disease_cleveland.parquet",
					"difficulty": difficulty,
					"seed": 11,
				}
			)
			self.assertGreater(prepared["df"].isna().sum().sum(), 0, difficulty)

	def test_generated_data_cleaning_injects_by_difficulty(self):
		from apps.exercises.missing_values import (
			inject_missing_values,
			prepare_generated_missing_values_exercise,
		)
		from apps.exercises.data_zoo import build_zoo_dataset
		import numpy as np
		import pandas as pd

		for difficulty in ("easy", "medium", "hard"):
			prepared = prepare_generated_missing_values_exercise(
				{
					"data_field": "marketing",
					"difficulty": difficulty,
					"seed": 21,
					"n_rows": 80,
				}
			)
			self.assertIn("target", prepared)
			self.assertIn("outcome", prepared)
			self.assertIn("reference_plot", prepared)
			missing = prepared["df"][prepared["target"]].isna().sum()
			self.assertGreater(missing, 0, difficulty)
			self.assertEqual(int(prepared["df"].isna().sum().sum()), int(missing), difficulty)
			# Only the target column should contain missing values.
			self.assertEqual(prepared["df"][prepared["outcome"]].isna().sum(), 0, difficulty)

		# Hard conditions on the target median; medium on the outcome median.
		clean = build_zoo_dataset("marketing", rows=80, seed=21)
		numeric = [
			c
			for c in clean.columns
			if pd.api.types.is_numeric_dtype(clean[c]) and not str(c).lower().endswith("_id")
		]
		rng = np.random.default_rng(21)
		target, outcome = [str(v) for v in rng.choice(numeric, size=2, replace=False)]
		clean[target] = pd.to_numeric(clean[target], errors="coerce").astype(float)
		clean[outcome] = pd.to_numeric(clean[outcome], errors="coerce").astype(float)

		_, easy_meta = inject_missing_values(clean, target, outcome, "easy", seed=21)
		self.assertIsNone(easy_meta["condition_column"])

		_, medium_meta = inject_missing_values(clean, target, outcome, "medium", seed=21)
		self.assertEqual(medium_meta["condition_column"], outcome)
		self.assertIn(medium_meta["condition_side"], {"above", "below"})

		_, hard_meta = inject_missing_values(clean, target, outcome, "hard", seed=21)
		self.assertEqual(hard_meta["condition_column"], target)
		self.assertIn(hard_meta["condition_side"], {"above", "below"})

	def test_dataset_without_two_floats_is_unavailable(self):
		from apps.exercises.dataframe_providers import prepare_exercise_namespace
		from apps.exercises.missing_values import DatasetUnavailableError, UNAVAILABLE_MESSAGE

		with self.assertRaises(DatasetUnavailableError) as ctx:
			prepare_exercise_namespace(
				{
					"dataframe_source": "missing_values",
					"data_field": "finance",
					"dataset_file": "02_population.parquet",
					"difficulty": "easy",
					"seed": 3,
				}
			)
		self.assertEqual(str(ctx.exception), UNAVAILABLE_MESSAGE)

	def test_run_notebook_reports_unavailable_dataset(self):
		result = run_notebook(
			cells=[{"source": "df.head()"}],
			allowed_imports=["numpy", "pandas", "matplotlib.pyplot"],
			data_state={
				"dataframe_source": "missing_values",
				"data_field": "finance",
				"dataset_file": "02_population.parquet",
				"difficulty": "easy",
				"seed": 3,
			},
			evaluation_rules={},
		)
		self.assertFalse(result["success"])
		self.assertIn("unavailable", (result.get("error") or "").lower())

	def test_medium_rejects_global_fill_but_accepts_outcome_guided_fill(self):
		seeded = Exercise.objects.get(slug="clean-messy-dataset")
		data_state = seeded.initial_data_state()
		data_state.update(
			{
				"data_field": "healthcare",
				"topic": "healthcare",
				"difficulty": "medium",
				"selected_feature": "medium",
				"seed": 7,
			}
		)
		global_fill = run_notebook(
			cells=[
				{"source": "df[target] = df[target].fillna(df[target].median())\ndf.head()"},
				{"source": "df.head()"},
			],
			allowed_imports=seeded.allowed_imports,
			data_state=data_state,
			evaluation_rules=seeded.evaluation_rules,
		)
		self.assertIsNone(global_fill.get("error"))
		self.assertFalse(global_fill["evaluation"]["passed"])

		outcome_fill = run_notebook(
			cells=[
				{
					"source": (
						"obs = df.dropna(subset=[target, outcome])\n"
						"slope, intercept = np.polyfit(obs[outcome], obs[target], 1)\n"
						"missing = df[target].isna()\n"
						"df.loc[missing, target] = slope * df.loc[missing, outcome] + intercept\n"
						"df.head()"
					)
				},
				{"source": "df.head()"},
			],
			allowed_imports=seeded.allowed_imports,
			data_state=data_state,
			evaluation_rules=seeded.evaluation_rules,
		)
		self.assertTrue(outcome_fill["success"], outcome_fill.get("error"))
		self.assertTrue(outcome_fill["evaluation"]["passed"])

	def test_hard_requires_accounting_for_deleted_side(self):
		seeded = Exercise.objects.get(slug="clean-messy-dataset")
		data_state = seeded.initial_data_state()
		data_state.update(
			{
				"data_field": "healthcare",
				"topic": "healthcare",
				"difficulty": "hard",
				"selected_feature": "hard",
				"seed": 9,
			}
		)
		medium_style = run_notebook(
			cells=[
				{
					"source": (
						"obs = df.dropna(subset=[target, outcome])\n"
						"slope, intercept = np.polyfit(obs[outcome], obs[target], 1)\n"
						"missing = df[target].isna()\n"
						"df.loc[missing, target] = slope * df.loc[missing, outcome] + intercept\n"
						"df.head()"
					)
				}
			],
			allowed_imports=seeded.allowed_imports,
			data_state=data_state,
			evaluation_rules=seeded.evaluation_rules,
		)
		self.assertIsNone(medium_style.get("error"))
		self.assertFalse(medium_style["evaluation"]["passed"])

		hard_style = run_notebook(
			cells=[
				{
					"source": (
						"obs = df.dropna(subset=[target, outcome])\n"
						"slope, intercept = np.polyfit(obs[outcome], obs[target], 1)\n"
						"missing = df[target].isna()\n"
						"preds = slope * df.loc[missing, outcome] + intercept\n"
						"vals = [float(v) for v in preds]\n"
						"obs_med = float(obs[target].median())\n"
						"asymm = float(obs[target].mean()) - obs_med\n"
						"spread = float(obs[target].std())\n"
						"if spread < 0:\n"
						"    spread = -spread\n"
						"if spread == 0:\n"
						"    spread = 1.0\n"
						"mean_val = sum(vals) / len(vals)\n"
						"if asymm < 0:\n"
						"    desired = obs_med - spread * 0.25\n"
						"    shift = desired - mean_val\n"
						"    if shift > 0:\n"
						"        shift = 0\n"
						"else:\n"
						"    desired = obs_med + spread * 0.25\n"
						"    shift = desired - mean_val\n"
						"    if shift < 0:\n"
						"        shift = 0\n"
						"vals = [v + shift for v in vals]\n"
						"df.loc[missing, target] = vals\n"
						"df.head()"
					)
				}
			],
			allowed_imports=seeded.allowed_imports,
			data_state=data_state,
			evaluation_rules=seeded.evaluation_rules,
		)
		self.assertTrue(hard_style["success"], hard_style.get("error"))
		self.assertTrue(hard_style["evaluation"]["passed"])

	def test_authenticated_run_stores_personal_exercise_progress(self):
		from apps.authentication.models import CustomUser, UserProfile

		user = CustomUser.objects.create_user(email="learner@example.com", password="pass12345")
		UserProfile.objects.create(
			user=user,
			nickname="learner-one",
			data_field="healthcare",
			dataset_file="01_heart_disease_cleveland.parquet",
			onboarding_complete=True,
		)
		self.client.force_login(user)
		seeded = Exercise.objects.get(slug="clean-messy-dataset")
		response = self.client.post(
			reverse("exercises:run", args=[seeded.slug]),
			data=json.dumps(
				{
					"cells": [{"source": "df.head()"}, {"source": "len(df)"}],
					"data_state": {
						**seeded.initial_data_state(),
						"difficulty": "medium",
						"selected_feature": "medium",
						"seed": 11,
					},
				}
			),
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		run_payload = response.json()
		self.assertEqual(len(run_payload["previous_attempts"]), 1)
		self.assertEqual(run_payload["previous_attempts"][0]["try_number"], 1)
		self.assertNotIn("seed", run_payload["previous_attempts"][0])

		user.profile.refresh_from_db()
		saved = user.profile.exercise_progress.get(seeded.slug)
		self.assertIsNotNone(saved)
		self.assertEqual(saved["data_state"]["difficulty"], "medium")
		self.assertEqual(saved["data_state"]["seed"], 11)
		self.assertNotIn("reference_plot", saved["data_state"])
		self.assertEqual(len(saved["attempts"]), 1)
		self.assertEqual(saved["attempts"][0]["try_number"], 1)
		self.assertEqual(saved["attempts"][0]["seed"], 11)

		listed = self.client.post(
			reverse("exercises:repeat", args=[seeded.slug]),
			data=b"{}",
			content_type="application/json",
		)
		self.assertEqual(listed.status_code, 200)
		list_payload = listed.json()
		self.assertTrue(list_payload["success"])
		self.assertEqual(list_payload["attempts"][0]["try_number"], 1)
		self.assertNotIn("seed", list_payload["attempts"][0])

		repeat = self.client.post(
			reverse("exercises:repeat", args=[seeded.slug]),
			data=json.dumps({"try_number": 1, "restore": True}),
			content_type="application/json",
		)
		self.assertEqual(repeat.status_code, 200)
		payload = repeat.json()
		self.assertTrue(payload["success"])
		self.assertEqual(payload["data_state"]["difficulty"], "medium")
		self.assertEqual(payload["data_state"]["seed"], 11)

		# A new seed creates try 2; the public list still omits seeds.
		self.client.post(
			reverse("exercises:run", args=[seeded.slug]),
			data=json.dumps(
				{
					"cells": [{"source": "df.head()"}, {"source": "len(df)"}],
					"data_state": {
						**seeded.initial_data_state(),
						"difficulty": "hard",
						"selected_feature": "hard",
						"seed": 22,
					},
				}
			),
			content_type="application/json",
		)
		user.profile.refresh_from_db()
		saved = user.profile.exercise_progress.get(seeded.slug)
		self.assertEqual(len(saved["attempts"]), 2)
		self.assertEqual(saved["attempts"][1]["try_number"], 2)
		self.assertEqual(saved["attempts"][1]["seed"], 22)

		listed = self.client.post(
			reverse("exercises:repeat", args=[seeded.slug]),
			data=b"{}",
			content_type="application/json",
		).json()
		self.assertEqual([item["try_number"] for item in listed["attempts"]], [1, 2])
		self.assertTrue(all("seed" not in item for item in listed["attempts"]))

		restored_first = self.client.post(
			reverse("exercises:repeat", args=[seeded.slug]),
			data=json.dumps({"try_number": 1, "restore": True}),
			content_type="application/json",
		).json()
		self.assertEqual(restored_first["data_state"]["seed"], 11)
		self.assertEqual(restored_first["data_state"]["difficulty"], "medium")

	def test_exercise_detail_shows_repeat_and_report_bug_controls(self):
		seeded = Exercise.objects.filter(is_placeholder=False, published=True).first()
		self.assertIsNotNone(seeded)
		response = self.client.get(reverse("exercises:detail", args=[seeded.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Repeat Previous Attempt")
		self.assertContains(response, "Report Bug")
		self.assertContains(response, "type=bug")
		self.assertNotContains(response, "Repeat Saved Attempt")


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
		# Zoo-backed insurance sample exposes age / charges style columns.
		self.assertTrue({"age", "charges", "bmi", "sex"} & set(df.columns) or len(df.columns) >= 3)

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
		self.assertIn("encoding", exercise.soft_skill_prompt.lower())
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


	def test_hard_mode_sometimes_joins_olist_for_ecommerce(self):
		from apps.exercises.data_transformation import (
			data_transformation_passes,
			prepare_data_transformation,
		)

		# join_probability=1 forces the Olist join path for ecommerce.
		prepared = prepare_data_transformation(
			"hard",
			seed=7,
			rows=40,
			topic="ecommerce",
			join_probability=1.0,
		)
		self.assertEqual(prepared["task"]["mode"], "join_transform")
		self.assertIsNotNone(prepared["df_extra"])
		self.assertIn("product_id", prepared["df"].columns)
		self.assertIn("product_category_name", prepared["df_extra"].columns)
		self.assertIn("join", prepared["task"]["prompt"].lower())
		self.assertTrue(
			data_transformation_passes(
				prepared["task"],
				df0=prepared["task"]["expected"]["df0"],
				df1=prepared["task"]["expected"]["df1"],
				df2=prepared["task"]["expected"]["df2"],
			)
		)

	def test_hard_join_placeholder_keeps_encoding_for_other_topics(self):
		from apps.exercises.data_transformation import prepare_data_transformation

		prepared = prepare_data_transformation(
			"hard",
			seed=7,
			rows=40,
			topic="retail",
			join_probability=1.0,
		)
		self.assertEqual(prepared["task"]["mode"], "advanced_encoding")
		self.assertIsNone(prepared["df_extra"])

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


class MessyDatasetTests(TestCase):
	def test_seeded_exercise_is_active(self):
		exercise = Exercise.objects.get(slug="data-cleaning-messy-dataset")
		self.assertFalse(exercise.is_placeholder)
		self.assertEqual(exercise.order, 30)
		self.assertEqual(exercise.data_definition.get("dataframe_source"), "messy_dataset")
		self.assertIn("pipeline", exercise.soft_skill_prompt.lower())
		self.assertIn("messy_dataset_passes", _rules_blob(exercise))
		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Features")
		self.assertContains(response, "pipeline")

	def test_difficulty_layers(self):
		from apps.exercises.messy_dataset import prepare_messy_dataset

		easy = prepare_messy_dataset("easy", seed=11, rows=40)
		self.assertIsNone(easy["df_extra"])
		self.assertTrue(str(easy["df"].columns[0]).startswith("col_"))
		self.assertIn("word_to_int", easy["task"])

		medium = prepare_messy_dataset("medium", seed=11, rows=40)
		self.assertIsNotNone(medium["df_extra"])
		self.assertIn("brand", medium["df_extra"].columns)
		self.assertIn("join", medium["task"]["prompt"].lower())

		hard = prepare_messy_dataset("hard", seed=11, rows=40)
		self.assertIsNotNone(hard["df_extra"])
		self.assertIn("type mismatch", hard["task"]["prompt"].lower())

	def test_notebook_passes_with_expected_clean_frame(self):
		exercise = Exercise.objects.get(slug="data-cleaning-messy-dataset")
		cells = [
			{"source": "df = task['expected_df'].copy()\ndf.head()"},
			{"source": "df.head()"},
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

	def test_notebook_fails_when_left_dirty(self):
		exercise = Exercise.objects.get(slug="data-cleaning-messy-dataset")
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


class AbTestingTests(TestCase):
	def test_seeded_exercise_is_active(self):
		exercise = Exercise.objects.get(slug="ab-testing-conditional-probability")
		self.assertFalse(exercise.is_placeholder)
		self.assertEqual(exercise.order, 60)
		self.assertEqual(exercise.data_definition.get("dataframe_source"), "ab_testing")
		self.assertIn("null hypothesis", exercise.soft_skill_prompt.lower())
		self.assertIn("ab_testing_passes", _rules_blob(exercise))
		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Features")
		self.assertContains(response, "null hypothesis")

	def test_difficulty_modes(self):
		from apps.exercises.ab_testing import prepare_ab_testing

		easy = prepare_ab_testing("easy", seed=5)
		self.assertEqual(easy["task"]["mode"], "ttest_decision")
		self.assertIsNotNone(easy["group_a"])
		self.assertIn("different", easy["task"]["prompt"])

		medium = prepare_ab_testing("medium", seed=5)
		self.assertEqual(medium["task"]["mode"], "bayes")
		self.assertIn("Bayes", medium["task"]["prompt"])
		self.assertIsNone(medium["group_a"])

		hard = prepare_ab_testing("hard", seed=5)
		self.assertEqual(hard["task"]["mode"], "ttest_relevance")
		p_value = hard["task"]["expected"]["p_value"]
		self.assertGreaterEqual(p_value, 0.11)
		self.assertLessEqual(p_value, 0.40)
		self.assertFalse(hard["task"]["expected"]["relevant"])

	def test_notebook_passes_with_expected_answers(self):
		exercise = Exercise.objects.get(slug="ab-testing-conditional-probability")
		for difficulty, source in (
			(
				"easy",
				"different = task['expected']['different']\n"
				"p_value = task['expected']['p_value']\n"
				"different",
			),
			(
				"medium",
				"answer = task['expected']['answer']\n"
				"answer",
			),
			(
				"hard",
				"different = task['expected']['different']\n"
				"relevant = task['expected']['relevant']\n"
				"p_value = task['expected']['p_value']\n"
				"relevant",
			),
		):
			data_state = exercise.initial_data_state()
			data_state["difficulty"] = difficulty
			data_state["selected_feature"] = difficulty
			result = run_notebook(
				cells=[{"source": source}, {"source": "len(df)"}],
				allowed_imports=exercise.allowed_imports,
				data_state=data_state,
				evaluation_rules=exercise.evaluation_rules,
			)
			self.assertTrue(result["success"], difficulty)
			self.assertTrue(result["evaluation"]["passed"], difficulty)

	def test_notebook_fails_without_decision(self):
		exercise = Exercise.objects.get(slug="ab-testing-conditional-probability")
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


class DescriptiveStatisticsTests(TestCase):
	def test_seeded_exercise_is_active(self):
		exercise = Exercise.objects.get(slug="descriptive-statistics")
		self.assertFalse(exercise.is_placeholder)
		self.assertEqual(exercise.order, 50)
		self.assertEqual(exercise.data_definition.get("dataframe_source"), "descriptive_statistics")
		self.assertIn("business context", exercise.soft_skill_prompt.lower())
		self.assertIn("descriptive_statistics_passes", _rules_blob(exercise))
		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Data Features")
		self.assertContains(response, "median")
		# Intro markdown headings should render as HTML, not raw ### markers.
		self.assertContains(response, "<h3>")
		self.assertNotContains(response, "### What to do")
		self.assertContains(response, "md-content")
		# Plotting bonus lives in a notebook markdown cell, not the task banner.
		self.assertIn("Plotting bonus", response.context.get("plotting_bonus_prompt") or "")
		self.assertIn("<h3>", response.context.get("plotting_bonus_prompt_html") or "")

	def test_difficulty_modes(self):
		from apps.exercises.descriptive_statistics import prepare_descriptive_statistics

		easy = prepare_descriptive_statistics("easy", seed=5)
		self.assertEqual(easy["task"]["mode"], "summary_batch")
		self.assertGreaterEqual(len(easy["task"]["expected"]), 3)
		self.assertLessEqual(len(easy["task"]["expected"]), 5)
		self.assertIn("answer", easy["task"]["prompt"])

		medium = prepare_descriptive_statistics("medium", seed=5)
		self.assertEqual(medium["task"]["mode"], "groupby_compare")
		self.assertIn("groupby", medium["task"]["prompt"])
		self.assertGreaterEqual(len(medium["task"]["expected"]), 3)

		hard_a = prepare_descriptive_statistics("hard", seed=5)
		hard_b = prepare_descriptive_statistics("hard", seed=6)
		self.assertIn(hard_a["task"]["mode"], {"bimodal_hist", "correlation_heatmap"})
		self.assertIn(hard_b["task"]["mode"], {"bimodal_hist", "correlation_heatmap"})
		self.assertTrue(hard_a["task"]["requires_plot"])

	def test_notebook_passes_with_expected_answers(self):
		exercise = Exercise.objects.get(slug="descriptive-statistics")
		for difficulty, source in (
			(
				"easy",
				"answer = dict(task['expected'])\nanswer",
			),
			(
				"medium",
				"answer = dict(task['expected'])\nanswer",
			),
			(
				"hard",
				"answer = dict(task['expected'])\n"
				"plotted = True\n"
				"answer",
			),
		):
			data_state = exercise.initial_data_state()
			data_state["difficulty"] = difficulty
			data_state["selected_feature"] = difficulty
			result = run_notebook(
				cells=[{"source": source}, {"source": "len(df)"}],
				allowed_imports=exercise.allowed_imports,
				data_state=data_state,
				evaluation_rules=exercise.evaluation_rules,
			)
			self.assertTrue(result["success"], difficulty)
			self.assertTrue(result["evaluation"]["passed"], difficulty)

	def test_notebook_fails_without_answers(self):
		exercise = Exercise.objects.get(slug="descriptive-statistics")
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

	def test_easy_never_asks_mode_for_float_only_within_variable(self):
		from apps.exercises.descriptive_statistics import prepare_descriptive_statistics

		for seed in range(20):
			prepared = prepare_descriptive_statistics("easy", seed=seed)
			prompt = prepared["task"]["prompt"].lower()
			if prepared["task"].get("family") != "within_variable":
				continue
			# Mode prompts should not target float columns income/spend/satisfaction.
			if "mode" not in prompt:
				continue
			for float_col in ("income", "spend", "satisfaction"):
				if f"mode" in prompt and float_col in prompt:
					# Allow mode of a categorical mentioned alongside a float mean/median,
					# but not "mode of `income`".
					self.assertNotIn(f"mode of `{float_col}`", prepared["task"]["prompt"].lower())


class MachineLearningTrackTests(TestCase):
	ML_SLUGS = (
		"ml-data-preparation",
		"ml-regression-strategies",
		"ml-intro-classification",
		"ml-advanced-classification",
		"ml-ensemble-methods",
		"ml-unsupervised-learning",
	)

	def test_track_and_exercises_are_active(self):
		track = Track.objects.get(slug="machine-learning-and-ai")
		self.assertFalse(track.is_placeholder)
		self.assertTrue(track.published)
		for slug in self.ML_SLUGS:
			exercise = Exercise.objects.get(slug=slug)
			self.assertFalse(exercise.is_placeholder, slug)
			self.assertTrue(exercise.published, slug)
			self.assertEqual(exercise.track_id, track.id, slug)
			self.assertIn("sklearn", exercise.allowed_imports)
			self.assertTrue(exercise.soft_skill_prompt.strip(), slug)
			self.assertIn("_passes", _rules_blob(exercise))
			response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
			self.assertEqual(response.status_code, 200, slug)

	def test_prepare_modes_and_expected_answers(self):
		from apps.exercises.ml_advanced_classification import (
			ml_advanced_classification_passes,
			prepare_ml_advanced_classification,
		)
		from apps.exercises.ml_classification import ml_classification_passes, prepare_ml_classification
		from apps.exercises.ml_data_prep import ml_data_prep_passes, prepare_ml_data_prep
		from apps.exercises.ml_ensembles import ml_ensembles_passes, prepare_ml_ensembles
		from apps.exercises.ml_regression import ml_regression_passes, prepare_ml_regression
		from apps.exercises.ml_unsupervised import ml_unsupervised_passes, prepare_ml_unsupervised

		cases = (
			(prepare_ml_data_prep, ml_data_prep_passes, {"easy": "split_check", "medium": "multi_split", "hard": "kfold_scaled"}),
			(prepare_ml_regression, ml_regression_passes, {"easy": "compare_two", "medium": "tune_one", "hard": "scaled_chosen"}),
			(prepare_ml_classification, ml_classification_passes, {"easy": "compare_three", "medium": "tune_one", "hard": "scaled_chosen"}),
			(
				prepare_ml_advanced_classification,
				ml_advanced_classification_passes,
				{"easy": "imbalance_report", "medium": "threshold_tune", "hard": "multiclass_cv"},
			),
			(prepare_ml_ensembles, ml_ensembles_passes, {"easy": "compare_two", "medium": "tune_two", "hard": "scaled_search"}),
			(prepare_ml_unsupervised, ml_unsupervised_passes, {"easy": "fixed_k", "medium": "choose_k", "hard": "pca_compare"}),
		)
		for prepare_fn, passer, modes in cases:
			for difficulty, mode in modes.items():
				prepared = prepare_fn(difficulty, seed=42)
				self.assertEqual(prepared["task"]["mode"], mode, f"{prepare_fn.__name__}:{difficulty}")
				self.assertTrue(
					passer(prepared["task"], answer=dict(prepared["task"]["expected"]), plotted=True),
					f"{prepare_fn.__name__}:{difficulty}",
				)

	def test_notebook_passes_with_expected_answers(self):
		for slug in self.ML_SLUGS:
			exercise = Exercise.objects.get(slug=slug)
			data_state = exercise.initial_data_state()
			data_state["difficulty"] = "easy"
			data_state["selected_feature"] = "easy"
			result = run_notebook(
				cells=[
					{"source": "answer = dict(task['expected'])\nanswer"},
					{"source": "len(df)"},
				],
				allowed_imports=exercise.allowed_imports,
				data_state=data_state,
				evaluation_rules=exercise.evaluation_rules,
			)
			self.assertTrue(result["success"], slug)
			self.assertTrue(result["evaluation"]["passed"], f"{slug}: {result['evaluation']}")

	def test_dataframe_providers_expose_ml_sources(self):
		from apps.exercises.dataframe_providers import prepare_exercise_namespace

		for source in (
			"ml_data_prep",
			"ml_regression",
			"ml_classification",
			"ml_advanced_classification",
			"ml_ensembles",
			"ml_unsupervised",
		):
			prepared = prepare_exercise_namespace(
				{"dataframe_source": source, "difficulty": "easy", "seed": 7}
			)
			self.assertIn("df", prepared, source)
			self.assertIn("task", prepared, source)
			self.assertIn("prompt", prepared["task"], source)

	def test_ml_sources_have_spotter_tips(self):
		from apps.exercises.spotter_tips import SPOTTER_TIPS, get_spotter_tips

		for slug in self.ML_SLUGS:
			exercise = Exercise.objects.get(slug=slug)
			source = (exercise.data_definition or {}).get("dataframe_source")
			self.assertIn(source, SPOTTER_TIPS, msg=slug)
			tips = get_spotter_tips(source)
			for level in ("easy", "medium", "hard"):
				self.assertGreaterEqual(len(tips[level]), 2, msg=f"{slug}:{level}")


class SpotterTipsTests(TestCase):
	def test_detail_page_includes_spotter_button_and_tips(self):
		exercise = Exercise.objects.get(slug="descriptive-statistics")
		response = self.client.get(reverse("exercises:detail", args=[exercise.slug]))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Spotter")
		self.assertContains(response, "spotter-tips-data")
		self.assertContains(response, "df['column'].mean()")

	def test_medium_and_hard_omit_earlier_level_tips(self):
		from apps.exercises.spotter_tips import get_spotter_tips

		tips = get_spotter_tips("descriptive_statistics")
		self.assertIn("df['column'].mean()", tips["easy"])
		self.assertNotIn("df['column'].mean()", tips["medium"])
		self.assertNotIn("df['column'].mean()", tips["hard"])
		self.assertTrue(any("groupby" in tip for tip in tips["medium"]))
		self.assertFalse(any("groupby" in tip for tip in tips["hard"]))
		self.assertTrue(any("corr" in tip or "hist" in tip for tip in tips["hard"]))

	def test_all_active_analytics_sources_have_spotter_tips(self):
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
				joined = " ".join(tips[level]).lower()
				self.assertNotIn("df['income']", joined)
				self.assertNotIn('df["income"]', joined)


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
		self.assertContains(response, "md-content")
		self.assertContains(response, "Post to forum")

	def test_submit_soft_skill_saves_without_forum_post(self):
		from apps.exercises.models import ExerciseAttempt
		from apps.forum.models import Post

		response = self.client.post(
			reverse("exercises:soft_skill", args=[self.exercise.slug]),
			{"soft_skill_response": "I would walk through the steps clearly."},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("exercises:detail", args=[self.exercise.slug]))

		attempt = ExerciseAttempt.objects.get(exercise=self.exercise)
		self.assertEqual(attempt.soft_skill_response, "I would walk through the steps clearly.")
		self.assertFalse(Post.objects.filter(content__icontains="Soft skill reflection").exists())

	def test_submit_soft_skill_posts_to_forum_when_selected(self):
		from apps.forum.models import Post, Topic

		response = self.client.post(
			reverse("exercises:soft_skill", args=[self.exercise.slug]),
			{
				"soft_skill_response": "I would share assumptions and ask for feedback.",
				"post_to_forum": "1",
			},
		)
		self.assertEqual(response.status_code, 302)
		topic = Topic.objects.get(exercise=self.exercise)
		self.assertEqual(response.url, topic.get_absolute_url())
		post = Post.objects.get(topic=topic)
		self.assertIn(self.exercise.soft_skill_prompt, post.content)
		self.assertIn("I would share assumptions and ask for feedback.", post.content)

	def test_submit_soft_skill_requires_response(self):
		response = self.client.post(
			reverse("exercises:soft_skill", args=[self.exercise.slug]),
			{"soft_skill_response": "   ", "post_to_forum": "1"},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("exercises:detail", args=[self.exercise.slug]))

	def test_submit_soft_skill_saves_when_forum_suspended(self):
		from apps.authentication.models import CustomUser
		from apps.exercises.models import ExerciseAttempt
		from apps.forum.models import Post

		# Establish forum identity, then suspend it.
		self.client.get(reverse("forum:index"))
		user = CustomUser.objects.get(token=self.client.session["forum_token"])
		user.is_forum_suspended = True
		user.save(update_fields=["is_forum_suspended"])

		response = self.client.post(
			reverse("exercises:soft_skill", args=[self.exercise.slug]),
			{
				"soft_skill_response": "Saved locally even though forum is suspended.",
				"post_to_forum": "1",
			},
		)
		self.assertEqual(response.status_code, 302)
		self.assertEqual(response.url, reverse("exercises:detail", args=[self.exercise.slug]))
		attempt = ExerciseAttempt.objects.get(exercise=self.exercise)
		self.assertEqual(
			attempt.soft_skill_response,
			"Saved locally even though forum is suspended.",
		)
		self.assertFalse(Post.objects.filter(content__icontains="Soft skill reflection").exists())


class PlottingBonusTests(TestCase):
	def test_source_plot_kinds_and_ab_randomization(self):
		from apps.exercises.plotting_bonus import build_plotting_bonus, resolve_plot_kind

		self.assertEqual(resolve_plot_kind("pandas_intro", seed=1), "any")
		self.assertEqual(resolve_plot_kind("data_transformation", seed=1), "bar")
		self.assertEqual(resolve_plot_kind("messy_dataset", seed=1), "histogram")
		self.assertEqual(resolve_plot_kind("missing_values", seed=1), "missingness_bar")
		self.assertEqual(resolve_plot_kind("descriptive_statistics", seed=1), "box")
		self.assertEqual(resolve_plot_kind("ab_testing", seed=0), "hist_overlap")
		self.assertEqual(resolve_plot_kind("ab_testing", seed=1), "violin")
		self.assertEqual(resolve_plot_kind("ml_data_prep", seed=1), "heatmap")
		self.assertEqual(resolve_plot_kind("ml_classification", seed=1), "confusion_matrix")
		self.assertEqual(resolve_plot_kind("ml_unsupervised", seed=1), "scatter")
		self.assertEqual(resolve_plot_kind("ml_regression", seed=0), "scatter")
		self.assertEqual(resolve_plot_kind("ml_regression", seed=1), "tree")

		easy = build_plotting_bonus("pandas_intro", difficulty="easy", seed=1)
		medium = build_plotting_bonus("data_transformation", difficulty="medium", seed=1)
		hard = build_plotting_bonus("messy_dataset", difficulty="hard", seed=1)
		self.assertEqual(easy["modifications_required"], 0)
		self.assertEqual(medium["modifications_required"], 1)
		self.assertEqual(hard["modifications_required"], 2)
		self.assertIn("Plotting bonus", easy["prompt"])

	def test_evaluate_accepts_any_plot_for_pandas_intro(self):
		from apps.exercises.plotting_bonus import build_plotting_bonus, evaluate_plotting_bonus

		bonus = build_plotting_bonus("pandas_intro", difficulty="easy", seed=3)
		result = evaluate_plotting_bonus(
			bonus=bonus,
			cell_sources=["plt.scatter(df['a'], df['b'])"],
			figure_count=1,
		)
		self.assertTrue(result["kind_matched"])
		self.assertTrue(result["passed"])
		self.assertEqual(result["plots_created"], 1)

	def test_medium_requires_one_style_mod_hard_requires_two(self):
		from apps.exercises.plotting_bonus import build_plotting_bonus, evaluate_plotting_bonus

		medium = build_plotting_bonus("data_transformation", difficulty="medium", seed=1)
		hard = build_plotting_bonus("data_transformation", difficulty="hard", seed=1)

		plain = evaluate_plotting_bonus(bonus=medium, cell_sources=["plt.bar(['a','b'], [1,2])"])
		self.assertTrue(plain["kind_matched"])
		self.assertFalse(plain["passed"])

		one_mod = evaluate_plotting_bonus(
			bonus=medium,
			cell_sources=["plt.bar(['a','b'], [1,2], color='teal')"],
		)
		self.assertTrue(one_mod["passed"])
		self.assertEqual(one_mod["modifications_count"], 1)

		one_on_hard = evaluate_plotting_bonus(
			bonus=hard,
			cell_sources=["plt.bar(['a','b'], [1,2], color='teal')"],
		)
		self.assertFalse(one_on_hard["passed"])

		two_on_hard = evaluate_plotting_bonus(
			bonus=hard,
			cell_sources=[
				"plt.bar(['a','b'], [1,2], color='navy')\nplt.title('Bands', fontsize=12)"
			],
		)
		self.assertTrue(two_on_hard["passed"])
		self.assertGreaterEqual(two_on_hard["modifications_count"], 2)

	def test_missingness_bar_and_histogram_and_box(self):
		from apps.exercises.plotting_bonus import build_plotting_bonus, evaluate_plotting_bonus

		missing = build_plotting_bonus("missing_values", difficulty="easy", seed=2)
		bar_only = evaluate_plotting_bonus(bonus=missing, cell_sources=["plt.bar(df.columns, [1,2])"])
		self.assertFalse(bar_only["kind_matched"])
		with_isna = evaluate_plotting_bonus(
			bonus=missing,
			cell_sources=["m = df.isna().sum()\nplt.bar(m.index, m.values)"],
		)
		self.assertTrue(with_isna["passed"])

		hist = build_plotting_bonus("messy_dataset", difficulty="easy", seed=2)
		self.assertTrue(
			evaluate_plotting_bonus(bonus=hist, cell_sources=["plt.hist(df['x'])"])["passed"]
		)

		box = build_plotting_bonus("descriptive_statistics", difficulty="easy", seed=2)
		self.assertTrue(
			evaluate_plotting_bonus(bonus=box, cell_sources=["plt.boxplot(df['x'])"])["passed"]
		)

	def test_ab_testing_hist_overlap_or_violin(self):
		from apps.exercises.plotting_bonus import build_plotting_bonus, evaluate_plotting_bonus

		overlap = build_plotting_bonus("ab_testing", difficulty="easy", seed=0)
		self.assertEqual(overlap["kind"], "hist_overlap")
		self.assertTrue(
			evaluate_plotting_bonus(
				bonus=overlap,
				cell_sources=[
					"plt.hist(group_a, alpha=0.5)\nplt.hist(group_b, alpha=0.5)"
				],
			)["passed"]
		)

		violin = build_plotting_bonus("ab_testing", difficulty="easy", seed=1)
		self.assertEqual(violin["kind"], "violin")
		self.assertTrue(
			evaluate_plotting_bonus(
				bonus=violin,
				cell_sources=["plt.violinplot([group_a, group_b])"],
			)["passed"]
		)

	def test_prepared_namespace_includes_plotting_bonus(self):
		from apps.exercises.dataframe_providers import prepare_exercise_namespace

		prepared = prepare_exercise_namespace(
			{"dataframe_source": "pandas_intro", "selected_feature": "easy", "seed": 11}
		)
		bonus = prepared["task"]["plotting_bonus"]
		self.assertTrue(bonus["enabled"])
		self.assertEqual(bonus["kind"], "any")
		self.assertIn("Plotting bonus", bonus["prompt"])
		self.assertNotIn("Plotting bonus", prepared["task"]["prompt"])

	def test_notebook_run_reports_plotting_bonus_without_failing_main(self):
		exercise = Exercise.objects.filter(slug="pandas-introduction").first()
		if exercise is None:
			self.skipTest("pandas-introduction not seeded")
		data_state = {
			"dataframe_source": "pandas_intro",
			"selected_feature": "easy",
			"seed": 42,
			"n_rows": 40,
		}
		result = run_notebook(
			cells=[{"source": "plt.plot([1, 2, 3], color='crimson')\nanswer = 0"}],
			allowed_imports=exercise.allowed_imports,
			data_state=data_state,
			evaluation_rules=exercise.evaluation_rules,
		)
		bonus = result["plotting_bonus"]
		self.assertTrue(bonus["kind_matched"])
		checks = result["evaluation"]["checks"]
		self.assertTrue(any(c.get("type") == "plotting_bonus" for c in checks))
		# Bonus check must not flip the main evaluation flag by itself.
		main_checks = [c for c in checks if c.get("type") != "plotting_bonus"]
		if main_checks and all(c.get("passed") for c in main_checks):
			self.assertTrue(result["evaluation"]["passed"])


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

	def test_evaluate_builds_rubric_and_hides_expected(self):
		from apps.exercises.grading import evaluate_with_graders, MODE_EVALUATE, frame_diff
		import pandas as pd
		rules = {
			"graders": [
				{"id": "eq", "type": "equals", "variable": "answer", "expected": 2, "section": "core", "next_action": "Recompute answer."},
				{"id": "approach", "type": "ast_process", "section": "approach", "require_any": ["mean"], "fragile": True},
			],
			"success_message": "Done.",
		}
		# Hard mode: tell what was wrong, never reveal the correct answer.
		result = evaluate_with_graders(
			{"answer": 1, "data": {"difficulty": "hard", "selected_feature": "hard"}},
			rules,
			mode=MODE_EVALUATE,
			cell_sources=["answer = 1"],
		)
		self.assertFalse(result["core_passed"])
		self.assertIn("core", result["rubric"])
		failed = next(c for c in result["checks"] if c["id"] == "eq")
		self.assertIn("incorrect", failed["message"].lower())
		self.assertIn("got 1", failed["message"])
		self.assertNotIn("correct_answer", failed)
		self.assertFalse(result["answer_feedback"]["revealed"])
		self.assertEqual(result["answer_feedback"]["policy"], "hide")
		self.assertNotIn("expected", failed.get("details") or {})
		diff = frame_diff(pd.DataFrame({"a": [1]}), pd.DataFrame({"a": [2]}))
		self.assertFalse(diff["equal"])
		self.assertTrue(diff["preview"][0].get("expected_hidden"))

	def test_answer_feedback_by_difficulty(self):
		from apps.exercises.grading import evaluate_with_graders, MODE_EVALUATE
		rules = {
			"graders": [
				{"id": "eq", "type": "equals", "variable": "answer", "expected": 42, "section": "core"},
			]
		}

		easy = evaluate_with_graders(
			{"answer": 7, "data": {"difficulty": "easy", "selected_feature": "easy"}},
			rules,
			mode=MODE_EVALUATE,
		)
		failed_easy = next(c for c in easy["checks"] if c["id"] == "eq")
		self.assertIn("got 7", failed_easy["message"])
		self.assertEqual(failed_easy.get("correct_answer"), "42")
		self.assertEqual(easy["answer_feedback"]["policy"], "show")
		self.assertTrue(easy["answer_feedback"]["revealed"])
		self.assertFalse(easy["answer_feedback"]["can_reveal"])

		medium = evaluate_with_graders(
			{"answer": 7, "data": {"difficulty": "medium", "selected_feature": "medium"}},
			rules,
			mode=MODE_EVALUATE,
			reveal_expected=False,
		)
		failed_medium = next(c for c in medium["checks"] if c["id"] == "eq")
		self.assertIn("got 7", failed_medium["message"])
		self.assertNotIn("correct_answer", failed_medium)
		self.assertTrue(failed_medium.get("can_reveal_answer"))
		self.assertEqual(medium["answer_feedback"]["policy"], "offer")
		self.assertTrue(medium["answer_feedback"]["can_reveal"])

		medium_revealed = evaluate_with_graders(
			{"answer": 7, "data": {"difficulty": "medium", "selected_feature": "medium"}},
			rules,
			mode=MODE_EVALUATE,
			reveal_expected=True,
		)
		failed_revealed = next(c for c in medium_revealed["checks"] if c["id"] == "eq")
		self.assertEqual(failed_revealed.get("correct_answer"), "42")
		self.assertFalse(medium_revealed["answer_feedback"]["can_reveal"])

		hard = evaluate_with_graders(
			{"answer": 7, "data": {"difficulty": "hard", "selected_feature": "hard"}},
			rules,
			mode=MODE_EVALUATE,
			reveal_expected=True,  # client cannot force-reveal on hard
		)
		failed_hard = next(c for c in hard["checks"] if c["id"] == "eq")
		self.assertIn("got 7", failed_hard["message"])
		self.assertNotIn("correct_answer", failed_hard)
		self.assertFalse(hard["answer_feedback"]["revealed"])
		self.assertFalse(hard["answer_feedback"]["can_reveal"])

	def test_task_assertion_feedback_includes_incorrect_values(self):
		from apps.exercises.grading import evaluate_with_graders, MODE_EVALUATE
		rules = {
			"graders": [
				{
					"id": "core",
					"type": "assertion",
					"expression": "answer == task['expected']",
					"section": "core",
					"failure_message": "Result does not match the task yet.",
				}
			]
		}
		result = evaluate_with_graders(
			{
				"answer": 3,
				"task": {"mode": "summary", "expected": 10},
				"data": {"difficulty": "easy", "selected_feature": "easy"},
			},
			rules,
			mode=MODE_EVALUATE,
		)
		failed = next(c for c in result["checks"] if c["id"] == "core")
		self.assertIn("Incorrect:", failed["message"])
		self.assertIn("was 3", failed["message"])
		self.assertIn("→ 10", failed.get("correct_answer", ""))

	def test_any_of_strategies_and_bands(self):
		from apps.exercises.grading import evaluate_with_graders, MODE_EVALUATE, BAND_PASS
		rules = {
			"graders": [
				{
					"id": "strat",
					"type": "any_of",
					"section": "core",
					"strategies": [
						{"id": "a", "graders": [{"type": "equals", "variable": "answer", "expected": 1}]},
						{"id": "b", "graders": [{"type": "equals", "variable": "answer", "expected": 2}]},
					],
				}
			],
			"soft_skill": {"required_for_full_completion": True, "min_chars": 10, "min_words": 3},
		}
		result = evaluate_with_graders(
			{"answer": 2},
			rules,
			mode=MODE_EVALUATE,
			soft_skill_response="too short",
			soft_skill_prompt="Reflect please",
		)
		self.assertTrue(result["core_passed"])
		self.assertEqual(result["matched_strategy"], "b")
		# Incomplete reflection is optional credit (like plotting bonus), not pass_with_issues.
		self.assertEqual(result["band"], BAND_PASS)
		reflection = next(c for c in result["checks"] if c["id"] == "soft_skill")
		self.assertFalse(reflection["passed"])
		self.assertIn("incomplete", reflection["message"].lower())

	def test_incomplete_reflection_matches_optional_bonus_style(self):
		from apps.exercises.grading import evaluate_with_graders, MODE_EVALUATE, BAND_PASS
		rules = {
			"graders": [
				{"id": "eq", "type": "equals", "variable": "answer", "expected": 2, "section": "core"},
			],
			"soft_skill": {"required_for_full_completion": True, "min_chars": 40, "min_words": 8},
			"success_message": "Core complete.",
		}
		empty = evaluate_with_graders(
			{"answer": 2},
			rules,
			mode=MODE_EVALUATE,
			soft_skill_response="",
			soft_skill_prompt="Reflect please",
			plotting_bonus={
				"attempted": False,
				"passed": False,
				"message": "Plotting bonus incomplete: still need a bar chart.",
			},
		)
		self.assertTrue(empty["core_passed"])
		self.assertEqual(empty["band"], BAND_PASS)
		self.assertEqual(empty["summary"], "Core complete.")
		reflection = next(c for c in empty["checks"] if c["id"] == "soft_skill")
		bonus = next(c for c in empty["checks"] if c["id"] == "plotting_bonus")
		self.assertFalse(reflection["passed"])
		self.assertFalse(bonus["passed"])
		self.assertIn("incomplete", reflection["message"].lower())
		self.assertIn("incomplete", bonus["message"].lower())
		self.assertEqual(empty["rubric"]["reflection"]["passed"], 0)
		self.assertEqual(empty["rubric"]["bonus"]["passed"], 0)

		done = evaluate_with_graders(
			{"answer": 2},
			rules,
			mode=MODE_EVALUATE,
			soft_skill_response="This is a sufficiently long reflection for credit here.",
			soft_skill_prompt="Reflect please",
		)
		reflection_ok = next(c for c in done["checks"] if c["id"] == "soft_skill")
		self.assertTrue(reflection_ok["passed"])
		self.assertIn("complete", reflection_ok["message"].lower())


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

	def test_dataframe_to_csv_is_blocked(self):
		result = run_notebook(
			cells=[{"source": "import pandas as pd\n"}],  # import blocked; use preloaded
			allowed_imports=["pandas"],
			data_state={"seed": 1},
			evaluation_rules={},
			mode="run",
		)
		# rebuild with valid cell
		result = run_notebook(
			cells=[{"source": "df = pd.DataFrame({'a':[1]})\ndf.to_csv('/tmp/out.csv')"}],
			allowed_imports=["pandas", "numpy", "matplotlib.pyplot"],
			data_state={"seed": 1},
			evaluation_rules={},
			mode="run",
		)
		error = (result["cells"][0].get("error") or "").lower()
		self.assertIn("permission", error)

	def test_environ_attr_access_blocked_by_ast(self):
		result = run_notebook(
			cells=[{"source": "x = pd.__file__"}],
			allowed_imports=["pandas", "numpy", "matplotlib.pyplot"],
			data_state={"seed": 1},
			evaluation_rules={},
			mode="run",
		)
		# __file__ starts with _ and is blocked as private attribute
		error = (result["cells"][0].get("error") or "").lower()
		self.assertTrue("blocked" in error or "private" in error)


class ExerciseRateLimitTests(TestCase):
	def setUp(self):
		from django.core.cache import cache
		cache.clear()
		self.track = Track.objects.create(title="Rate Track", slug="rate-track", published=True)
		self.exercise = Exercise.objects.create(
			track=self.track,
			title="Rate Exercise",
			slug="rate-exercise",
			starter_code="# %%\nanswer = 1",
			allowed_imports=["math"],
			data_definition={"initial_data": {"seed": 1}},
			evaluation_rules={"required_variables": ["answer"]},
			published=True,
		)

	def test_rate_limit_helper_blocks_after_limit(self):
		from django.test import RequestFactory
		from apps.exercises.rate_limit import check_rate_limit
		factory = RequestFactory()
		req = factory.post("/x/")
		from django.contrib.sessions.middleware import SessionMiddleware
		middleware = SessionMiddleware(lambda r: None)
		middleware.process_request(req)
		req.session.save()
		for _ in range(3):
			ok, _retry = check_rate_limit(req, action="unit-test-limit", limit=3, window_seconds=60)
			self.assertTrue(ok)
		ok, retry = check_rate_limit(req, action="unit-test-limit", limit=3, window_seconds=60)
		self.assertFalse(ok)
		self.assertGreaterEqual(retry, 1)

	def test_forwarded_for_is_ignored_without_trusted_proxies(self):
		from django.test import RequestFactory, override_settings
		from project_core.ratelimit import client_ip

		factory = RequestFactory()
		req = factory.post("/x/", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8", REMOTE_ADDR="10.0.0.1")
		with override_settings(TRUSTED_PROXY_COUNT=0):
			self.assertEqual(client_ip(req), "10.0.0.1")
		with override_settings(TRUSTED_PROXY_COUNT=1):
			self.assertEqual(client_ip(req), "5.6.7.8")

	def test_spoofed_forwarded_for_cannot_reset_the_counter(self):
		from django.test import RequestFactory, override_settings
		from project_core.ratelimit import check_rate_limit
		from django.contrib.sessions.middleware import SessionMiddleware

		factory = RequestFactory()
		middleware = SessionMiddleware(lambda r: None)
		with override_settings(TRUSTED_PROXY_COUNT=0):
			for index in range(3):
				req = factory.post("/x/", HTTP_X_FORWARDED_FOR=f"9.9.9.{index}", REMOTE_ADDR="10.0.0.2")
				middleware.process_request(req)
				ok, _retry = check_rate_limit(req, action="spoof-test", limit=3, window_seconds=60, by_ip_only=True)
				self.assertTrue(ok)
			req = factory.post("/x/", HTTP_X_FORWARDED_FOR="9.9.9.99", REMOTE_ADDR="10.0.0.2")
			middleware.process_request(req)
			ok, _retry = check_rate_limit(req, action="spoof-test", limit=3, window_seconds=60, by_ip_only=True)
			self.assertFalse(ok)


class ExerciseInputValidationTests(TestCase):
	def setUp(self):
		self.track = Track.objects.create(title="Input Track", slug="input-track", published=True)
		self.exercise = Exercise.objects.create(
			track=self.track,
			title="Input Exercise",
			slug="input-exercise",
			starter_code="# %%\nanswer = 1",
			allowed_imports=["math"],
			data_definition={"initial_data": {"seed": 1}},
			evaluation_rules={"required_variables": ["answer"]},
			published=True,
		)

	def test_malformed_json_returns_400_not_500(self):
		for name in ("run", "reset", "repeat"):
			with self.subTest(endpoint=name):
				response = self.client.post(
					reverse(f"exercises:{name}", args=[self.exercise.slug]),
					data=b"{not json",
					content_type="application/json",
				)
				self.assertEqual(response.status_code, 400)
				self.assertFalse(response.json()["success"])

	def test_non_object_json_body_is_rejected(self):
		response = self.client.post(
			reverse("exercises:run", args=[self.exercise.slug]),
			data=b"[1, 2, 3]",
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)

	def test_client_supplied_row_count_is_clamped(self):
		from apps.exercises.dataframe_providers import MAX_GENERATED_ROWS, _row_count

		self.assertEqual(_row_count({"n_rows": 10**9}, 80), MAX_GENERATED_ROWS)
		self.assertEqual(_row_count({"n_rows": -5}, 80), 10)
		self.assertEqual(_row_count({"n_rows": "abc"}, 80), 80)
		self.assertEqual(_row_count({}, 80), 80)
		self.assertEqual(_row_count({"n_rows": 120}, 80), 120)

	def test_oversized_row_request_does_not_build_a_huge_frame(self):
		from apps.exercises.dataframe_providers import MAX_GENERATED_ROWS, prepare_exercise_namespace

		prepared = prepare_exercise_namespace(
			{
				"dataframe_source": "pandas_intro",
				"difficulty": "easy",
				"seed": 1,
				"n_rows": 500_000,
			}
		)
		self.assertLessEqual(len(prepared["df"]), MAX_GENERATED_ROWS)


class SandboxLanguageFeatureTests(TestCase):
	def _validate(self, source):
		import ast
		from apps.exercises.services import _validate_imports

		_validate_imports(ast.parse(source, mode="exec"), ["pandas"])

	def test_lambda_and_bitwise_not_are_available(self):
		self._validate("out = df['a'].apply(lambda v: v * 2)")
		self._validate("out = sorted([3, 1], key=lambda v: -v)")
		self._validate("out = df[~df['a'].isna()]")

	def test_lambda_body_is_still_validated(self):
		for source in (
			"out = df['a'].apply(lambda v: open('/etc/passwd'))",
			"out = df['a'].apply(lambda v: v.__class__)",
			"out = df['a'].apply(lambda v: __import__('os'))",
		):
			with self.subTest(source=source):
				with self.assertRaises(ValueError):
					self._validate(source)

	def test_blocked_features_explain_the_alternative(self):
		import ast
		from apps.exercises.services import _validate_imports

		with self.assertRaises(ValueError) as ctx:
			_validate_imports(ast.parse("def f(x):\n    return x", mode="exec"), ["pandas"])
		self.assertIn("lambda", str(ctx.exception).lower())

		with self.assertRaises(ValueError) as ctx:
			_validate_imports(ast.parse("with open('x') as f:\n    pass", mode="exec"), ["pandas"])
		self.assertIn("file", str(ctx.exception).lower())
