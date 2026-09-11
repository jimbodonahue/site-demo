from __future__ import annotations

from copy import deepcopy
from typing import Any

from apps.exercises.data_transformation import (
	build_product_dataframe,
	generate_data_transformation_task,
)
from apps.exercises.pandas_intro import build_patient_dataframe, generate_pandas_intro_task

DATAFRAME_NAME = "df"


def _difficulty(data_state: dict) -> str:
	return (
		data_state.get("selected_feature")
		or data_state.get("difficulty")
		or "easy"
	)


def _build_pandas_intro_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = data_state.get("seed", 42)
	df = build_patient_dataframe(rows=data_state.get("n_rows", 80), seed=seed)
	task = generate_pandas_intro_task(df, difficulty=difficulty, seed=seed)
	return {DATAFRAME_NAME: df, "task": task, "answer": None}


def _build_data_transformation_context(data_state: dict) -> dict[str, Any]:
	difficulty = _difficulty(data_state)
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = data_state.get("seed", 42)
	df = build_product_dataframe(rows=data_state.get("n_rows", 90), seed=seed)
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

	if source == "pandas_intro":
		return _build_pandas_intro_context(state)
	if source == "data_transformation":
		return _build_data_transformation_context(state)

	raise ValueError(f"Unknown dataframe_source: {source}")


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
