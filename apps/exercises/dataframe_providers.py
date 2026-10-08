from __future__ import annotations

from copy import deepcopy
from typing import Any

from apps.exercises.ab_testing import prepare_ab_testing
from apps.exercises.data_transformation import (
	prepare_data_transformation,
)
from apps.exercises.descriptive_statistics import prepare_descriptive_statistics
from apps.exercises.messy_dataset import prepare_messy_dataset
from apps.exercises.missing_values import (
	DatasetUnavailableError,
	UNAVAILABLE_MESSAGE,
	prepare_generated_missing_values_exercise,
	prepare_missing_values_exercise,
)
try:
	from apps.exercises.ml_advanced_classification import prepare_ml_advanced_classification
	from apps.exercises.ml_classification import prepare_ml_classification
	from apps.exercises.ml_data_prep import prepare_ml_data_prep
	from apps.exercises.ml_ensembles import prepare_ml_ensembles
	from apps.exercises.ml_regression import prepare_ml_regression
	from apps.exercises.ml_unsupervised import prepare_ml_unsupervised
except ImportError:  # pragma: no cover - lite hosts omit sklearn/xgboost
	def _ml_unavailable(*_args, **_kwargs):
		raise RuntimeError(
			"Machine learning packages (scikit-learn / xgboost) are not installed on this host."
		)

	prepare_ml_advanced_classification = _ml_unavailable
	prepare_ml_classification = _ml_unavailable
	prepare_ml_data_prep = _ml_unavailable
	prepare_ml_ensembles = _ml_unavailable
	prepare_ml_regression = _ml_unavailable
	prepare_ml_unsupervised = _ml_unavailable

from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task
from apps.exercises.markdown_utils import render_markdown_html
from apps.exercises.data_zoo import sample_zoo_dataframe, sector_label
from apps.exercises.plotting_bonus import attach_plotting_bonus_to_prepared

DATAFRAME_NAME = "df"

# Row counts arrive inside the client-supplied data_state, so they are clamped
# before any generator allocates a frame or fits a model on it.
MAX_GENERATED_ROWS = 2000
MIN_GENERATED_ROWS = 10


def _row_count(data_state: dict, default: int) -> int:
	"""Clamp the requested dataset size to a range the sandbox can afford."""
	try:
		rows = int(data_state.get("n_rows", default))
	except (TypeError, ValueError):
		return default
	return max(MIN_GENERATED_ROWS, min(rows, MAX_GENERATED_ROWS))


def _difficulty(data_state: dict) -> str:
	return (
		data_state.get("selected_feature")
		or data_state.get("difficulty")
		or "easy"
	)


def _build_missing_values_context(data_state: dict) -> dict[str, Any]:
	try:
		return prepare_missing_values_exercise(data_state)
	except DatasetUnavailableError:
		raise DatasetUnavailableError(UNAVAILABLE_MESSAGE)


def _build_data_quality_context(data_state: dict) -> dict[str, Any]:
	"""Data Cleaning: Missing Values — inject target NAs by difficulty; plot vs outcome."""
	try:
		return prepare_generated_missing_values_exercise(data_state)
	except DatasetUnavailableError:
		raise DatasetUnavailableError(UNAVAILABLE_MESSAGE)


def _zoo_kwargs(data_state: dict) -> dict[str, Any]:
	return {
		"data_field": data_state.get("data_field") or data_state.get("topic"),
		"dataset_file": data_state.get("dataset_file"),
		"topic": data_state.get("topic") or data_state.get("data_field"),
	}


def _build_zoo_explore_context(data_state: dict) -> dict[str, Any]:
	topic = (
		data_state.get("topic")
		or data_state.get("data_field")
		or "healthcare"
	)
	seed = int(data_state.get("seed", 42) or 42)
	rows = _row_count(data_state, 800)
	frame = sample_zoo_dataframe(
		str(topic),
		rows=rows,
		seed=seed,
		dataset_file=data_state.get("dataset_file"),
	)
	dataset_file = str(data_state.get("dataset_file") or "").strip()
	label = sector_label(str(topic))
	prompt = (
		f"Explore the **{label}** Data Zoo dataset"
		+ (f" (`{dataset_file}`)" if dataset_file else "")
		+ f". The working table is `df` ({len(frame)} rows × {frame.shape[1]} columns)."
	)
	return {
		DATAFRAME_NAME: frame,
		"task": {
			"prompt": prompt,
			"topic": str(topic),
			"dataset_file": dataset_file,
		},
	}


def _build_pandas_intro_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = data_state.get("seed", 42)
	df = build_patient_dataframe(
		rows=_row_count(data_state, 80),
		seed=seed,
		**_zoo_kwargs(data_state),
	)
	task = generate_pandas_intro_task(df, difficulty=difficulty, seed=seed)
	return {DATAFRAME_NAME: df, "task": task, "answer": None}


def _build_data_transformation_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = data_state.get("seed", 42)
	prepared = prepare_data_transformation(
		difficulty=difficulty,
		seed=seed,
		rows=_row_count(data_state, 90),
		**_zoo_kwargs(data_state),
	)
	return {
		DATAFRAME_NAME: prepared["df"],
		"df_extra": prepared.get("df_extra"),
		"task": prepared["task"],
		"df0": prepared.get("df0"),
		"df1": prepared.get("df1"),
		"df2": prepared.get("df2"),
	}


def _build_messy_dataset_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	prepared = prepare_messy_dataset(
		difficulty=difficulty,
		seed=data_state.get("seed", 42),
		rows=_row_count(data_state, 48),
		**_zoo_kwargs(data_state),
	)
	return {
		DATAFRAME_NAME: prepared["df"],
		"df_extra": prepared["df_extra"],
		"task": prepared["task"],
	}


def _build_ab_testing_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	prepared = prepare_ab_testing(
		difficulty=difficulty,
		seed=data_state.get("seed", 42),
		**_zoo_kwargs(data_state),
	)
	return prepared


def _build_descriptive_statistics_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	return prepare_descriptive_statistics(
		difficulty=difficulty,
		seed=data_state.get("seed", 42),
		rows=_row_count(data_state, 120),
		**_zoo_kwargs(data_state),
	)


def _build_ml_context(prepare_fn, data_state: dict, *, default_rows: int = 100) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	return prepare_fn(
		difficulty=difficulty,
		seed=data_state.get("seed", 42),
		rows=_row_count(data_state, default_rows),
		**_zoo_kwargs(data_state),
	)


def prepare_exercise_namespace(data_state: dict | None) -> dict[str, Any]:
	"""Build preloaded exercise objects. The working table is always named ``df``."""
	state = deepcopy(data_state or {})
	source = (state.get("dataframe_source") or "").strip()
	if not source:
		return {}

	# Default zoo sectors when the attempt has not chosen a topic yet.
	# Profile preference is applied upstream in views._with_dataset_selection.
	from apps.exercises.data_zoo import default_sector_for_source

	if not (state.get("data_field") or state.get("topic")):
		state["data_field"] = default_sector_for_source(source)
		state["topic"] = state["data_field"]

	if source == "zoo_explore":
		return _build_zoo_explore_context(state)
	if source == "pandas_intro":
		prepared = _build_pandas_intro_context(state)
	elif source == "data_transformation":
		prepared = _build_data_transformation_context(state)
	elif source == "messy_dataset":
		prepared = _build_messy_dataset_context(state)
	elif source == "ab_testing":
		prepared = _build_ab_testing_context(state)
	elif source == "descriptive_statistics":
		prepared = _build_descriptive_statistics_context(state)
	elif source == "missing_values":
		prepared = _build_missing_values_context(state)
	elif source == "data_quality":
		prepared = _build_data_quality_context(state)
	elif source == "ml_data_prep":
		prepared = _build_ml_context(prepare_ml_data_prep, state)
	elif source == "ml_regression":
		prepared = _build_ml_context(prepare_ml_regression, state)
	elif source == "ml_classification":
		prepared = _build_ml_context(prepare_ml_classification, state)
	elif source == "ml_advanced_classification":
		prepared = _build_ml_context(prepare_ml_advanced_classification, state, default_rows=110)
	elif source == "ml_ensembles":
		prepared = _build_ml_context(prepare_ml_ensembles, state)
	elif source == "ml_unsupervised":
		prepared = _build_ml_context(prepare_ml_unsupervised, state)
	else:
		raise ValueError(f"Unknown dataframe_source: {source}")

	return attach_plotting_bonus_to_prepared(
		prepared,
		source=source,
		difficulty=_difficulty(state),
		seed=int(state.get("seed", 42) or 42),
	)


def dataframe_head_html(df: Any, rows: int = 10) -> str:
	"""Return a compact HTML table for the Exercise Graphic panel."""
	if df is None or not hasattr(df, "head"):
		return ""
	try:
		preview = df.head(rows)
		return preview.to_html(
			classes="dataframe-preview",
			border=0,
			index=True,
			justify="left",
			max_cols=12,
			escape=True,
		)
	except Exception:
		return ""


def enrich_data_state_visuals(data_state: dict | None) -> dict[str, Any]:
	"""Attach reference_plot and/or dataset_preview_html for the exercise side panel.

	Exercises with a graph keep ``reference_plot``. Otherwise the working table
	``df`` is summarized with ``dataset_preview_html`` so the panel is never empty.
	"""
	state = deepcopy(data_state or {})
	state.pop("dataset_preview_html", None)
	try:
		prepared = prepare_exercise_namespace(state)
	except Exception:
		return state

	reference_plot = prepared.get("reference_plot")
	if reference_plot:
		state["reference_plot"] = reference_plot
		return state

	html = dataframe_head_html(prepared.get(DATAFRAME_NAME))
	if html:
		state["dataset_preview_html"] = html
	return state


def extract_task_prompt(data_state: dict | None) -> str:
	"""Return the generated task prompt for exercises that expose a ``task`` object."""
	try:
		prepared = prepare_exercise_namespace(data_state)
	except Exception:
		return ""
	task = prepared.get("task")
	if isinstance(task, dict):
		return str(task.get("prompt") or "").strip()
	return ""


def render_task_prompt_html(prompt: str | None) -> str:
	"""Sanitize Markdown task prompts for the exercise Task banner."""
	return render_markdown_html(prompt or "")
