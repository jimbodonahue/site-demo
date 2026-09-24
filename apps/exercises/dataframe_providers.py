from __future__ import annotations

from copy import deepcopy
from typing import Any

from apps.exercises.data_transformation import (
	build_product_dataframe,
	generate_data_transformation_task,
)
from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task
from apps.exercises.plotting_bonus import attach_plotting_bonus_to_prepared

DATAFRAME_NAME = "df"


def _difficulty(data_state: dict) -> str:
	return (
		data_state.get("selected_feature")
		or data_state.get("difficulty")
		or "easy"
	)


def _zoo_kwargs(data_state: dict) -> dict[str, Any]:
	return {
		"data_field": data_state.get("data_field") or data_state.get("topic"),
		"dataset_file": data_state.get("dataset_file"),
		"topic": data_state.get("topic") or data_state.get("data_field"),
	}


def _build_pandas_intro_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = data_state.get("seed", 42)
	df = build_patient_dataframe(
		rows=data_state.get("n_rows", 80),
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
	df = build_product_dataframe(
		rows=data_state.get("n_rows", 90),
		seed=seed,
		**_zoo_kwargs(data_state),
	)
	task = generate_data_transformation_task(df, difficulty=difficulty, seed=seed)
	return {
		DATAFRAME_NAME: df,
		"task": task,
		"df0": None,
		"df1": None,
		"df2": None,
	}


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

	if source == "pandas_intro":
		prepared = _build_pandas_intro_context(state)
	elif source == "data_transformation":
		prepared = _build_data_transformation_context(state)
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
