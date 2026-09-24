from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from apps.exercises.data_zoo import load_zoo_dataset_file

CACHE_DIR = Path(__file__).resolve().parent / "zoo_data" / "_missing_values_cache"
UNAVAILABLE_MESSAGE = "This data set is unavailable."
DEFAULT_SECTOR = "healthcare"
DEFAULT_DATASET_FILE = "01_heart_disease_cleveland.parquet"


class DatasetUnavailableError(ValueError):
	"""Raised when a selected zoo dataset cannot be used for this exercise."""


def _float_columns(df: pd.DataFrame) -> list[str]:
	return [column for column in df.columns if pd.api.types.is_float_dtype(df[column])]


def _eligible_numeric_columns(df: pd.DataFrame) -> list[str]:
	"""Numeric columns suitable as target/outcome (skip id-like fields)."""
	columns: list[str] = []
	for column in df.columns:
		if not pd.api.types.is_numeric_dtype(df[column]):
			continue
		lower = str(column).lower()
		if lower == "id" or lower.endswith("_id"):
			continue
		columns.append(column)
	return columns


def _as_float_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
	result = df.copy()
	for column in columns:
		result[column] = pd.to_numeric(result[column], errors="coerce").astype(float)
	return result


def _missing_rate(rng: np.random.Generator) -> float:
	return float(rng.uniform(0.20, 0.35))


def _serialize_index(index_values: Any) -> list[str]:
	return [str(value) for value in index_values]


def _index_from_keys(df: pd.DataFrame, keys: list[str]) -> pd.Index:
	lookup = {str(label): label for label in df.index}
	return pd.Index([lookup[key] for key in keys if key in lookup])


def _apply_easy_missingness(
	df: pd.DataFrame,
	target: str,
	rng: np.random.Generator,
) -> tuple[pd.DataFrame, dict[str, Any]]:
	result = df.copy()
	n_rows = len(result)
	if n_rows == 0:
		return result, {
			"missing_indices": [],
			"true_values": {},
			"condition_side": None,
			"condition_column": None,
			"condition_median": None,
		}

	rate = _missing_rate(rng)
	n_missing = max(1, int(round(n_rows * rate)))
	n_missing = min(n_missing, n_rows)
	rows = rng.choice(result.index.to_numpy(), size=n_missing, replace=False)
	true_values = {str(idx): float(result.loc[idx, target]) for idx in rows}
	result.loc[rows, target] = np.nan
	return result, {
		"missing_indices": _serialize_index(rows),
		"true_values": true_values,
		"condition_side": None,
		"condition_column": None,
		"condition_median": None,
	}


def _apply_conditioned_missingness(
	df: pd.DataFrame,
	target: str,
	condition_column: str,
	rng: np.random.Generator,
) -> tuple[pd.DataFrame, dict[str, Any]]:
	result = df.copy()
	if len(result) == 0:
		return result, {
			"missing_indices": [],
			"true_values": {},
			"condition_side": None,
			"condition_column": condition_column,
			"condition_median": None,
		}

	median_value = float(result[condition_column].median())
	use_above = bool(rng.random() < 0.5)
	if use_above:
		eligible = result.index[result[condition_column] > median_value]
		side = "above"
	else:
		eligible = result.index[result[condition_column] < median_value]
		side = "below"

	if len(eligible) == 0:
		eligible = result.index[result[condition_column] != median_value]
	if len(eligible) == 0:
		eligible = result.index

	rate = _missing_rate(rng)
	n_missing = max(1, int(round(len(eligible) * rate)))
	n_missing = min(n_missing, len(eligible))
	rows = rng.choice(eligible.to_numpy(), size=n_missing, replace=False)
	true_values = {str(idx): float(result.loc[idx, target]) for idx in rows}
	result.loc[rows, target] = np.nan
	return result, {
		"missing_indices": _serialize_index(rows),
		"true_values": true_values,
		"condition_side": side,
		"condition_column": condition_column,
		"condition_median": median_value,
	}


def inject_missing_values(
	df: pd.DataFrame,
	target: str,
	outcome: str,
	difficulty: str,
	seed: int = 42,
) -> tuple[pd.DataFrame, dict[str, Any]]:
	"""Insert difficulty-dependent missingness into ``target`` only."""
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		raise ValueError("Unknown difficulty. Use easy, medium, or hard.")

	rng = np.random.default_rng(seed)
	if difficulty_key == "easy":
		return _apply_easy_missingness(df, target, rng)
	if difficulty_key == "medium":
		return _apply_conditioned_missingness(df, target, outcome, rng)
	return _apply_conditioned_missingness(df, target, target, rng)


def _cache_key(sector: str, dataset_file: str, difficulty: str, seed: int) -> str:
	raw = f"{sector}|{dataset_file}|{difficulty}|{seed}"
	return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _generated_cache_key(sector: str, difficulty: str, seed: int, n_rows: int) -> str:
	raw = f"generated|{sector}|{difficulty}|{seed}|{n_rows}"
	return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _ensure_cache_dir() -> Path:
	CACHE_DIR.mkdir(parents=True, exist_ok=True)
	return CACHE_DIR


def _meta_paths(sector: str, dataset_file: str, difficulty: str, seed: int) -> tuple[Path, Path]:
	cache_dir = _ensure_cache_dir()
	key = _cache_key(sector, dataset_file, difficulty, seed)
	return cache_dir / f"{key}.parquet", cache_dir / f"{key}.json"


def _generated_meta_paths(
	sector: str, difficulty: str, seed: int, n_rows: int
) -> tuple[Path, Path]:
	cache_dir = _ensure_cache_dir()
	key = _generated_cache_key(sector, difficulty, seed, n_rows)
	return cache_dir / f"{key}.parquet", cache_dir / f"{key}.json"


def load_missing_values_meta(data_state: dict[str, Any]) -> dict[str, Any]:
	sector = (data_state.get("data_field") or data_state.get("topic") or DEFAULT_SECTOR).strip()
	difficulty = str(
		data_state.get("selected_feature") or data_state.get("difficulty") or "easy"
	).lower().strip()
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = int(data_state.get("seed", 42))

	dataset_file = (data_state.get("dataset_file") or "").strip()
	if dataset_file:
		_parquet_path, meta_path = _meta_paths(sector, dataset_file, difficulty, seed)
	else:
		n_rows = int(data_state.get("n_rows", 40) or 40)
		_parquet_path, meta_path = _generated_meta_paths(sector, difficulty, seed, n_rows)

	if not meta_path.exists():
		raise FileNotFoundError("Missing-values metadata was not found for this scenario.")
	return json.loads(meta_path.read_text(encoding="utf-8"))


def _build_reference_plot(df: pd.DataFrame, target: str, outcome: str) -> dict[str, str]:
	plot_df = df.dropna(subset=[target, outcome])
	figure = plt.figure(figsize=(6, 4))
	ax = figure.add_subplot(111)
	if len(plot_df):
		ax.scatter(plot_df[target], plot_df[outcome], alpha=0.7)
		if len(plot_df) >= 2:
			slope, intercept = np.polyfit(plot_df[target], plot_df[outcome], 1)
			x_line = np.linspace(plot_df[target].min(), plot_df[target].max(), 100)
			ax.plot(x_line, slope * x_line + intercept, color="crimson", linewidth=2)
	ax.set_xlabel(target)
	ax.set_ylabel(outcome)
	ax.set_title(f"{target} vs {outcome}")
	figure.tight_layout()

	buffer = io.BytesIO()
	figure.savefig(buffer, format="png")
	plt.close(figure)
	return {
		"mime_type": "image/png",
		"base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
	}


def _outcome_aware_expectations(
	baseline: pd.DataFrame,
	target: str,
	outcome: str,
	missing_index: pd.Index,
) -> np.ndarray:
	"""Predict missing target values from the second float column."""
	observed = baseline.dropna(subset=[target, outcome])
	if len(observed) < 2:
		fill = float(baseline[target].median())
		return np.full(len(missing_index), fill, dtype=float)

	x = observed[outcome].to_numpy(dtype=float)
	y = observed[target].to_numpy(dtype=float)
	if np.allclose(x, x[0]):
		fill = float(np.median(y))
		return np.full(len(missing_index), fill, dtype=float)

	slope, intercept = np.polyfit(x, y, 1)
	x_missing = baseline.loc[missing_index, outcome].to_numpy(dtype=float)
	return slope * x_missing + intercept


def _mae(left: np.ndarray, right: np.ndarray) -> float:
	return float(np.mean(np.abs(left - right)))


def missing_values_imputation_passes(
	df: Any,
	df_baseline: Any,
	target: Any,
	outcome: Any,
	data: Any,
) -> bool:
	"""Evaluate filled values with difficulty-aware expectations."""
	if not isinstance(df, pd.DataFrame) or not isinstance(df_baseline, pd.DataFrame):
		return False
	if not isinstance(target, str) or not isinstance(outcome, str):
		return False
	if target not in df.columns or outcome not in df.columns:
		return False
	if int(df.isna().sum().sum()) != 0:
		return False

	data_state = data if isinstance(data, dict) else {}
	difficulty = str(
		data_state.get("selected_feature") or data_state.get("difficulty") or "easy"
	).lower().strip()
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"

	try:
		meta = load_missing_values_meta(data_state)
	except Exception:
		# Fall back to a no-NA check when metadata is unavailable.
		return True

	missing_index = _index_from_keys(df_baseline, meta.get("missing_indices") or [])
	if len(missing_index) == 0:
		return True

	student_vals = df.loc[missing_index, target].to_numpy(dtype=float)
	if np.isnan(student_vals).any():
		return False

	observed_median = float(df_baseline[target].median())
	global_vals = np.full(len(missing_index), observed_median, dtype=float)
	true_map = meta.get("true_values") or {}
	true_vals = np.array(
		[float(true_map[str(idx)]) for idx in missing_index if str(idx) in true_map],
		dtype=float,
	)

	if difficulty == "easy":
		return True

	outcome_vals = _outcome_aware_expectations(df_baseline, target, outcome, missing_index)
	student_to_outcome = _mae(student_vals, outcome_vals)
	global_to_outcome = _mae(global_vals, outcome_vals)

	# Require that the fill is meaningfully closer to an outcome-aware prediction
	# than a single global constant fill.
	used_second_variable = student_to_outcome <= (global_to_outcome * 0.9 + 1e-9)
	if not used_second_variable and len(true_vals) == len(student_vals):
		# Accept if the student is clearly closer to the hidden true values than global fill.
		used_second_variable = _mae(student_vals, true_vals) < _mae(global_vals, true_vals)

	if difficulty == "medium":
		return used_second_variable

	# Hard: require an outcome-aware fill that also lands on the deleted
	# higher/lower side of the target distribution.
	if not used_second_variable:
		return False

	side = meta.get("condition_side")
	condition_median = meta.get("condition_median")
	if side not in {"above", "below"} or condition_median is None:
		return False

	imputed_mean = float(np.mean(student_vals))
	median_value = float(condition_median)
	if side == "above":
		return imputed_mean > median_value
	return imputed_mean < median_value


def prepare_missing_values_exercise(data_state: dict[str, Any]) -> dict[str, Any]:
	"""Load a zoo dataset, inject missing values, and cache the transformed frame."""
	sector = (data_state.get("data_field") or DEFAULT_SECTOR).strip()
	dataset_file = (data_state.get("dataset_file") or DEFAULT_DATASET_FILE).strip()
	difficulty = (
		data_state.get("selected_feature")
		or data_state.get("difficulty")
		or "easy"
	)
	difficulty = str(difficulty).lower().strip()
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = int(data_state.get("seed", 42))

	parquet_path, meta_path = _meta_paths(sector, dataset_file, difficulty, seed)

	if parquet_path.exists() and meta_path.exists():
		df = pd.read_parquet(parquet_path)
		meta = json.loads(meta_path.read_text(encoding="utf-8"))
		target = meta["target"]
		outcome = meta["outcome"]
	else:
		try:
			source = load_zoo_dataset_file(sector, dataset_file)
		except Exception as exc:  # pragma: no cover - defensive path
			raise DatasetUnavailableError(UNAVAILABLE_MESSAGE) from exc

		clean = source.dropna().copy()
		float_cols = _float_columns(clean)
		if len(float_cols) < 2:
			raise DatasetUnavailableError(UNAVAILABLE_MESSAGE)

		rng = np.random.default_rng(seed)
		selected = rng.choice(float_cols, size=2, replace=False)
		target = str(selected[0])
		outcome = str(selected[1])
		df, inject_meta = inject_missing_values(clean, target, outcome, difficulty, seed=seed)

		meta = {
			"target": target,
			"outcome": outcome,
			"sector": sector,
			"dataset_file": dataset_file,
			"difficulty": difficulty,
			"seed": seed,
			**inject_meta,
		}
		df.to_parquet(parquet_path, index=False)
		meta_path.write_text(json.dumps(meta), encoding="utf-8")

	baseline = df.copy()
	reference_plot = _build_reference_plot(baseline, target, outcome)
	return {
		"df": df,
		"df_baseline": baseline,
		"target": target,
		"outcome": outcome,
		"reference_plot": reference_plot,
	}


def prepare_generated_missing_values_exercise(data_state: dict[str, Any]) -> dict[str, Any]:
	"""Build a Data Zoo sector sample, inject missingness into target, plot vs outcome."""
	from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, build_zoo_dataset

	sector = (data_state.get("data_field") or data_state.get("topic") or "marketing").strip().lower()
	if sector not in DATA_SCIENCE_SECTORS:
		sector = "marketing"
	difficulty = str(
		data_state.get("selected_feature") or data_state.get("difficulty") or "easy"
	).lower().strip()
	if difficulty not in {"easy", "medium", "hard"}:
		difficulty = "easy"
	seed = int(data_state.get("seed", 42) or 42)
	n_rows = int(data_state.get("n_rows", 80) or 80)

	parquet_path, meta_path = _generated_meta_paths(sector, difficulty, seed, n_rows)

	if parquet_path.exists() and meta_path.exists():
		df = pd.read_parquet(parquet_path)
		meta = json.loads(meta_path.read_text(encoding="utf-8"))
		target = meta["target"]
		outcome = meta["outcome"]
	else:
		clean = build_zoo_dataset(sector, rows=n_rows, seed=seed)
		candidates = _eligible_numeric_columns(clean)
		if len(candidates) < 2:
			raise DatasetUnavailableError(UNAVAILABLE_MESSAGE)

		rng = np.random.default_rng(seed)
		selected = [str(value) for value in rng.choice(candidates, size=2, replace=False)]
		target, outcome = selected[0], selected[1]
		clean = _as_float_frame(clean, selected)
		df, inject_meta = inject_missing_values(clean, target, outcome, difficulty, seed=seed)

		meta = {
			"target": target,
			"outcome": outcome,
			"sector": sector,
			"difficulty": difficulty,
			"seed": seed,
			"n_rows": n_rows,
			**inject_meta,
		}
		df.to_parquet(parquet_path, index=False)
		meta_path.write_text(json.dumps(meta), encoding="utf-8")

	baseline = df.copy()
	reference_plot = _build_reference_plot(baseline, target, outcome)
	return {
		"df": df,
		"df_baseline": baseline,
		"target": target,
		"outcome": outcome,
		"reference_plot": reference_plot,
		"topic": sector,
		"data_field": sector,
	}
