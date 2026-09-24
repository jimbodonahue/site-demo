from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from apps.exercises.data_zoo import sample_zoo_dataframe

DEFAULT_SECTOR = "insurance"
DEFAULT_DATASET_FILE = "01_medical_cost_personal_dataset.parquet"
DEFAULT_ROWS = 80

# Fallback column role hints when a zoo frame is unusually sparse.
_PREFERRED_NUMERIC = (
	"age",
	"bmi",
	"charges",
	"children",
	"trestbps",
	"chol",
	"thalach",
	"admission_age",
	"medication_cost",
	"severity_score",
	"length_of_stay_days",
	"readmission_risk",
)
_PREFERRED_CATEGORICAL = (
	"sex",
	"smoker",
	"smoking_status",
	"region",
	"department",
	"insurance_type",
	"discharge_status",
	"cp",
)


def _sector_from_state(**kwargs: Any) -> str:
	sector = (
		kwargs.get("data_field")
		or kwargs.get("topic")
		or kwargs.get("sector")
		or DEFAULT_SECTOR
	)
	return str(sector).strip().lower() or DEFAULT_SECTOR


def classify_intro_columns(df: pd.DataFrame) -> dict[str, list[str]]:
	"""Split a zoo frame into numeric / categorical / selectable columns."""
	numeric: list[str] = []
	categorical: list[str] = []
	for column in df.columns:
		series = df[column]
		if pd.api.types.is_bool_dtype(series):
			categorical.append(str(column))
			continue
		if pd.api.types.is_numeric_dtype(series):
			# Low-cardinality numerics behave better as categoricals for filters.
			nunique = int(series.nunique(dropna=True))
			if 1 < nunique <= 8 and not pd.api.types.is_float_dtype(series):
				categorical.append(str(column))
			else:
				numeric.append(str(column))
			continue
		nunique = int(series.nunique(dropna=True))
		if 1 < nunique <= 24:
			categorical.append(str(column))

	# Prefer well-known teaching columns when present.
	numeric = [c for c in _PREFERRED_NUMERIC if c in numeric] + [
		c for c in numeric if c not in _PREFERRED_NUMERIC
	]
	categorical = [c for c in _PREFERRED_CATEGORICAL if c in categorical] + [
		c for c in categorical if c not in _PREFERRED_CATEGORICAL
	]

	if not numeric:
		# Last resort: coerce object columns that look numeric.
		for column in df.columns:
			coerced = pd.to_numeric(df[column], errors="coerce")
			if coerced.notna().mean() >= 0.8:
				numeric.append(str(column))
				df[column] = coerced

	selectable = list(dict.fromkeys([*categorical, *numeric]))
	sortable = list(dict.fromkeys([*numeric, *categorical]))
	return {
		"numeric": numeric,
		"categorical": categorical,
		"selectable": selectable,
		"sortable": sortable,
	}


def _prepare_intro_frame(df: pd.DataFrame) -> pd.DataFrame:
	"""Light cleanup so filters and summaries are stable."""
	out = df.copy()
	# Drop identifier-like columns with all-unique values (poor for filtering).
	drop_cols = []
	for column in out.columns:
		series = out[column]
		if pd.api.types.is_numeric_dtype(series):
			continue
		nunique = int(series.nunique(dropna=True))
		if nunique >= max(40, int(0.9 * len(out))):
			drop_cols.append(column)
	if drop_cols and len(out.columns) - len(drop_cols) >= 3:
		out = out.drop(columns=drop_cols)

	# Fill remaining nulls so student filters stay simple.
	for column in out.columns:
		series = out[column]
		if pd.api.types.is_numeric_dtype(series):
			out[column] = series.fillna(series.median() if series.notna().any() else 0)
		else:
			mode = series.mode(dropna=True)
			fill = mode.iloc[0] if not mode.empty else "unknown"
			out[column] = series.fillna(fill).astype(str)

	# Normalize common sex / smoker label spellings when present.
	if "sex" in out.columns:
		mapped = (
			out["sex"]
			.astype(str)
			.str.strip()
			.str.lower()
			.replace({"0": "female", "1": "male", "f": "female", "m": "male"})
		)
		out["sex"] = mapped
	if "smoker" in out.columns and "smoking_status" not in out.columns:
		out = out.rename(columns={"smoker": "smoking_status"})
		out["smoking_status"] = (
			out["smoking_status"]
			.astype(str)
			.str.strip()
			.str.lower()
			.replace({"0": "no", "1": "yes", "false": "no", "true": "yes"})
		)

	roles = classify_intro_columns(out)
	if len(roles["numeric"]) < 1 or len(roles["selectable"]) < 2:
		# Fall back to generated healthcare zoo schema if the parquet is unusable.
		from apps.exercises.data_zoo import build_zoo_dataset

		out = build_zoo_dataset("healthcare", rows=max(40, len(out)), seed=42)
	return out.reset_index(drop=True)


def build_patient_dataframe(
	rows: int = DEFAULT_ROWS,
	seed: int = 42,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> pd.DataFrame:
	"""Load a Data Zoo sample for the pandas introduction exercise."""
	sector = _sector_from_state(data_field=data_field, topic=topic)
	file_name = (dataset_file or "").strip()
	if not file_name and sector == DEFAULT_SECTOR:
		file_name = DEFAULT_DATASET_FILE
	frame = sample_zoo_dataframe(
		sector,
		rows=max(10, int(rows)),
		seed=seed,
		dataset_file=file_name or None,
	)
	return _prepare_intro_frame(frame)


def _human_column_list(columns: list[str]) -> str:
	if len(columns) == 1:
		return columns[0]
	if len(columns) == 2:
		return f"{columns[0]} and {columns[1]}"
	return ", ".join(columns[:-1]) + f", and {columns[-1]}"


def _format_condition(column: str, operator: str, value: Any) -> str:
	if operator == "==":
		if isinstance(value, str):
			return f"{column} is '{value}'"
		return f"{column} is {value}"
	if operator == "!=":
		if isinstance(value, str):
			return f"{column} is not '{value}'"
		return f"{column} is not {value}"
	labels = {
		">": "greater than",
		">=": "greater than or equal to",
		"<": "less than",
		"<=": "less than or equal to",
	}
	return f"{column} is {labels[operator]} {value}"


def _pick_columns(
	rng: np.random.Generator,
	selectable: list[str],
	count: int | None = None,
) -> list[str]:
	n = count if count is not None else int(rng.integers(1, min(4, len(selectable) + 1)))
	n = max(1, min(n, len(selectable)))
	chosen = list(rng.choice(selectable, size=n, replace=False))
	return [column for column in selectable if column in chosen]


def _apply_condition(frame: pd.DataFrame, column: str, operator: str, value: Any) -> pd.Series:
	series = frame[column]
	if operator == "==":
		return series == value
	if operator == "!=":
		return series != value
	if operator == ">":
		return series > value
	if operator == ">=":
		return series >= value
	if operator == "<":
		return series < value
	if operator == "<=":
		return series <= value
	raise ValueError(f"Unsupported operator: {operator}")


def _choose_numeric_condition(
	rng: np.random.Generator,
	df: pd.DataFrame,
	numeric_columns: list[str],
	used_columns: set[str],
	*,
	inequality_only: bool = False,
) -> dict[str, Any]:
	del inequality_only  # all numeric picks use inequalities / equality on ints
	candidates = [col for col in numeric_columns if col not in used_columns]
	if not candidates:
		raise ValueError("No numeric columns available for a filter.")
	column = str(rng.choice(candidates))
	series = pd.to_numeric(df[column], errors="coerce")
	low = float(series.quantile(0.25))
	high = float(series.quantile(0.75))
	if not np.isfinite(low) or not np.isfinite(high) or low == high:
		low = float(series.min())
		high = float(series.max())
	if pd.api.types.is_integer_dtype(df[column]) or series.dropna().mod(1).eq(0).all():
		low_i, high_i = int(np.floor(low)), int(np.ceil(high))
		value: Any = int(rng.integers(low_i, high_i + 1)) if low_i < high_i else int(series.median())
	else:
		value = round(float(rng.uniform(low, high if high > low else low + 1.0)), 2)
	operator = str(rng.choice([">", ">=", "<", "<="]))
	return {"column": column, "operator": operator, "value": value}


def _choose_categorical_condition(
	rng: np.random.Generator,
	df: pd.DataFrame,
	categorical_columns: list[str],
	used_columns: set[str],
) -> dict[str, Any]:
	candidates = [col for col in categorical_columns if col not in used_columns]
	if not candidates:
		raise ValueError("No categorical columns available for a filter.")
	column = str(rng.choice(candidates))
	values = sorted({value for value in df[column].tolist()})
	value = values[int(rng.integers(0, len(values)))]
	operator = str(rng.choice(["==", "!="]))
	return {"column": column, "operator": operator, "value": value}


def _choose_conditions(
	rng: np.random.Generator,
	df: pd.DataFrame,
	count: int,
	roles: dict[str, list[str]],
	*,
	require_inequality: bool = False,
) -> list[dict[str, Any]]:
	conditions: list[dict[str, Any]] = []
	used: set[str] = set()
	numeric = roles["numeric"]
	categorical = roles["categorical"]
	for index in range(count):
		if require_inequality and index == 0 and numeric:
			condition = _choose_numeric_condition(rng, df, numeric, used, inequality_only=True)
		else:
			prefer_numeric = index == 0 or rng.random() < 0.6
			if prefer_numeric and any(col not in used for col in numeric):
				condition = _choose_numeric_condition(rng, df, numeric, used)
			elif any(col not in used for col in categorical):
				condition = _choose_categorical_condition(rng, df, categorical, used)
			elif any(col not in used for col in numeric):
				condition = _choose_numeric_condition(rng, df, numeric, used)
			else:
				break
		conditions.append(condition)
		used.add(condition["column"])
	if not conditions:
		raise ValueError("Could not build filter conditions from zoo columns.")
	return conditions


def _mask_from_conditions(df: pd.DataFrame, conditions: list[dict[str, Any]]) -> pd.Series:
	mask = pd.Series(True, index=df.index)
	for condition in conditions:
		mask &= _apply_condition(df, condition["column"], condition["operator"], condition["value"])
	return mask


def _choose_sort(
	rng: np.random.Generator,
	columns: list[str],
	sortable: list[str],
) -> dict[str, Any]:
	pool = [col for col in columns if col in sortable] or list(sortable) or list(columns)
	column = str(rng.choice(pool))
	ascending = bool(rng.choice([True, False]))
	return {"column": column, "ascending": ascending}


def _easy_summary_specs(df: pd.DataFrame) -> list[dict[str, Any]]:
	"""Build a large pool of single-variable summary prompts from the live zoo frame."""
	roles = classify_intro_columns(df)
	specs: list[dict[str, Any]] = []

	for column in roles["numeric"]:
		series = pd.to_numeric(df[column], errors="coerce").dropna()
		if series.empty:
			continue
		as_int = series.dropna().mod(1).eq(0).all()
		max_expected: Any = int(series.max()) if as_int else round(float(series.max()), 2)
		min_expected: Any = int(series.min()) if as_int else round(float(series.min()), 2)
		specs.extend(
			[
				{
					"prompt": f"What is the maximum {column} in the dataset?",
					"expected": max_expected,
					"column": column,
					"stat": "max",
				},
				{
					"prompt": f"What is the minimum {column} in the dataset?",
					"expected": min_expected,
					"column": column,
					"stat": "min",
				},
				{
					"prompt": f"What is the median {column} in the dataset?",
					"expected": float(series.median()) if not as_int else float(series.median()),
					"column": column,
					"stat": "median",
				},
				{
					"prompt": f"What is the mean {column} in the dataset? Round to 2 decimal places.",
					"expected": round(float(series.mean()), 2),
					"column": column,
					"stat": "mean_rounded",
				},
			]
		)

	for column in roles["categorical"]:
		for value in sorted({v for v in df[column].tolist()}):
			specs.append(
				{
					"prompt": f"How many rows have {column} equal to '{value}'?",
					"expected": int((df[column] == value).sum()),
					"column": column,
					"stat": "count_value",
				}
			)
		specs.append(
			{
				"prompt": f"How many unique values does the '{column}' column have?",
				"expected": int(df[column].nunique()),
				"column": column,
				"stat": "nunique",
			}
		)

	specs.extend(
		[
			{
				"prompt": "How many rows are in the dataset?",
				"expected": int(len(df)),
				"column": None,
				"stat": "nrows",
			},
			{
				"prompt": "How many columns are in the dataset?",
				"expected": int(df.shape[1]),
				"column": None,
				"stat": "ncols",
			},
		]
	)
	return specs


def _build_easy_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	specs = _easy_summary_specs(df)
	if not specs:
		raise ValueError("No summary specs available for zoo frame.")
	spec = specs[int(rng.integers(0, len(specs)))]
	return {
		"difficulty": "easy",
		"mode": "summary",
		"prompt": spec["prompt"] + " Assign the result to `answer`.",
		"columns": [spec["column"]] if spec["column"] else [],
		"conditions": [],
		"extra": {"kind": "summary", "stat": spec["stat"]},
		"expected": spec["expected"],
		"expected_df": pd.DataFrame(),
	}


def _build_medium_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	roles = classify_intro_columns(df)
	condition_count = 1 if rng.random() < 0.7 else 2
	conditions = _choose_conditions(rng, df, condition_count, roles)
	column_count = int(rng.integers(1, min(4, len(roles["selectable"]) + 1)))
	columns = _pick_columns(rng, roles["selectable"], count=column_count)

	working = df.loc[_mask_from_conditions(df, conditions), columns].copy().reset_index(drop=True)
	prompt = (
		f"Return a dataframe with the {_human_column_list(columns)} of all rows where "
		+ " and ".join(_format_condition(c["column"], c["operator"], c["value"]) for c in conditions)
		+ ". Assign the result to `df`."
	)
	return {
		"difficulty": "medium",
		"mode": "subset",
		"prompt": prompt,
		"columns": columns,
		"conditions": conditions,
		"extra": None,
		"expected": None,
		"expected_df": working,
	}


def _build_hard_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	roles = classify_intro_columns(df)
	condition_count = 1 if rng.random() < 0.65 else 2
	conditions = _choose_conditions(rng, df, condition_count, roles, require_inequality=True)
	column_count = int(rng.integers(2, min(5, len(roles["selectable"]) + 1)))
	columns = _pick_columns(rng, roles["selectable"], count=max(2, column_count))

	sort_spec = _choose_sort(rng, columns, roles["sortable"])
	if sort_spec["column"] not in columns:
		columns = [sort_spec["column"]] + [c for c in columns if c != sort_spec["column"]]

	working = df.loc[_mask_from_conditions(df, conditions), columns].copy()
	working = working.sort_values(
		sort_spec["column"],
		ascending=sort_spec["ascending"],
	).reset_index(drop=True)

	direction = "ascending" if sort_spec["ascending"] else "descending"
	sort_phrase = f"sorted by {sort_spec['column']} in {direction} order"
	prompt = (
		f"Return a dataframe with the {_human_column_list(columns)} of all rows where "
		+ " and ".join(_format_condition(c["column"], c["operator"], c["value"]) for c in conditions)
		+ f", {sort_phrase}. Assign the result to `df`."
	)
	return {
		"difficulty": "hard",
		"mode": "sorted_subset",
		"prompt": prompt,
		"columns": columns,
		"conditions": conditions,
		"extra": {"kind": "sort", **sort_spec},
		"expected": None,
		"expected_df": working,
	}


def generate_pandas_intro_task(
	df: pd.DataFrame,
	difficulty: str = "easy",
	seed: int = 42,
) -> dict[str, Any]:
	"""Generate a reproducible pandas prompt and expected answer."""
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		raise ValueError("Unknown difficulty. Use easy, medium, or hard.")

	builders = {
		"easy": _build_easy_task,
		"medium": _build_medium_task,
		"hard": _build_hard_task,
	}
	builder = builders[difficulty_key]

	last_error: Exception | None = None
	for attempt in range(16):
		attempt_rng = np.random.default_rng(int(seed) + attempt * 97)
		try:
			task = builder(df, attempt_rng)
			if difficulty_key == "easy":
				return task
			if len(task["expected_df"]) > 0:
				return task
		except Exception as exc:  # pragma: no cover - defensive retry path
			last_error = exc
			continue

	if last_error:
		raise last_error
	return _build_easy_task(df, np.random.default_rng(seed))


def scalars_match(actual: Any, expected: Any) -> bool:
	"""Compare a student summary answer to the expected scalar."""
	from apps.exercises.grading import values_equal

	return values_equal(actual, expected, atol=1e-6, rtol=1e-6)


def dataframes_match(result_df: Any, expected_df: Any) -> bool:
	"""Compare student output to the expected dataframe with light normalization."""
	from apps.exercises.grading import frame_equal

	return frame_equal(result_df, expected_df, ignore_index=True, ignore_column_order=True)


def pandas_intro_task_passes(task: dict[str, Any], df: Any = None, answer: Any = None) -> bool:
	"""Validate either a summary scalar (`answer`) or a result dataframe (`df`)."""
	if task.get("mode") == "summary":
		return scalars_match(answer, task.get("expected"))
	return dataframes_match(df, task.get("expected_df"))
