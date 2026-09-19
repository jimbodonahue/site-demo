from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

FIRST_NAMES = [
	"Ava",
	"Ben",
	"Chloe",
	"Diego",
	"Elena",
	"Farah",
	"Gabriel",
	"Hannah",
	"Ivan",
	"Jade",
	"Kai",
	"Lina",
	"Marco",
	"Nina",
	"Omar",
	"Priya",
	"Quinn",
	"Rosa",
	"Samir",
	"Talia",
	"Uma",
	"Victor",
	"Wendy",
	"Xavier",
	"Yuki",
	"Zane",
	"Amir",
	"Bella",
	"Carlos",
	"Dana",
]

LAST_NAMES = [
	"Nguyen",
	"Patel",
	"Garcia",
	"Smith",
	"Kim",
	"Lopez",
	"Brown",
	"Ali",
	"Chen",
	"Rossi",
	"Silva",
	"Murphy",
	"Khan",
	"Martin",
	"Sato",
]

SELECTABLE_COLUMNS = [
	"first_name",
	"last_name",
	"age",
	"sex",
	"insurance",
	"blood_pressure",
	"cholesterol",
	"smoking_status",
	"department",
]

NUMERIC_COLUMNS = ["age", "insurance", "blood_pressure", "cholesterol"]
CATEGORICAL_COLUMNS = ["sex", "smoking_status", "department", "insurance"]
SORTABLE_COLUMNS = [
	"last_name",
	"first_name",
	"age",
	"blood_pressure",
	"cholesterol",
	"insurance",
	"department",
]


def build_patient_dataframe(rows: int = 80, seed: int = 42) -> pd.DataFrame:
	"""Build a small patient table suited to introductory pandas tasks."""
	rng = np.random.default_rng(seed)
	n = max(10, int(rows))

	first = rng.choice(FIRST_NAMES, size=n, replace=True)
	last = rng.choice(LAST_NAMES, size=n, replace=True)

	return pd.DataFrame(
		{
			"first_name": first,
			"last_name": last,
			"age": rng.integers(18, 90, size=n),
			"sex": rng.choice(["female", "male"], size=n),
			"insurance": rng.choice([0, 1], size=n, p=[0.45, 0.55]),
			"blood_pressure": rng.integers(90, 180, size=n),
			"cholesterol": rng.integers(120, 280, size=n),
			"smoking_status": rng.choice(["never", "former", "current"], size=n),
			"department": rng.choice(
				["cardiology", "general", "endocrinology", "pulmonology"],
				size=n,
			),
		}
	)


def _human_column_list(columns: list[str]) -> str:
	if len(columns) == 1:
		return columns[0]
	if len(columns) == 2:
		return f"{columns[0]} and {columns[1]}"
	return ", ".join(columns[:-1]) + f", and {columns[-1]}"


def _format_condition(column: str, operator: str, value: Any) -> str:
	if column == "insurance" and operator == "==":
		return "has insurance" if int(value) == 1 else "does not have insurance"
	if column == "insurance" and operator == "!=":
		return "does not have insurance" if int(value) == 1 else "has insurance"
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


def _pick_columns(rng: np.random.Generator, count: int | None = None) -> list[str]:
	n = count if count is not None else int(rng.integers(1, 4))
	chosen = list(rng.choice(SELECTABLE_COLUMNS, size=min(n, len(SELECTABLE_COLUMNS)), replace=False))
	return [column for column in SELECTABLE_COLUMNS if column in chosen]


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
	used_columns: set[str],
	*,
	inequality_only: bool = False,
) -> dict[str, Any]:
	candidates = [col for col in NUMERIC_COLUMNS if col not in used_columns]
	# Prefer continuous measures for inequality-focused hard tasks.
	if inequality_only:
		continuous = [col for col in candidates if col != "insurance"]
		if continuous:
			candidates = continuous
	column = str(rng.choice(candidates))
	series = df[column]
	if column == "insurance" and not inequality_only:
		value = int(rng.choice([0, 1]))
		operator = "=="
	else:
		low, high = int(series.quantile(0.25)), int(series.quantile(0.75))
		if low == high:
			low = int(series.min())
			high = int(series.max())
		value = int(rng.integers(low, high + 1)) if low < high else int(series.median())
		operator = str(rng.choice([">", ">=", "<", "<="]))
	return {"column": column, "operator": operator, "value": value}


def _choose_categorical_condition(
	rng: np.random.Generator,
	df: pd.DataFrame,
	used_columns: set[str],
) -> dict[str, Any]:
	candidates = [col for col in CATEGORICAL_COLUMNS if col not in used_columns]
	column = str(rng.choice(candidates))
	values = sorted({value for value in df[column].tolist()})
	value = values[int(rng.integers(0, len(values)))]
	operator = str(rng.choice(["==", "!="]))
	return {"column": column, "operator": operator, "value": value}


def _choose_conditions(
	rng: np.random.Generator,
	df: pd.DataFrame,
	count: int,
	*,
	require_inequality: bool = False,
) -> list[dict[str, Any]]:
	conditions: list[dict[str, Any]] = []
	used: set[str] = set()
	for index in range(count):
		if require_inequality and index == 0:
			condition = _choose_numeric_condition(rng, df, used, inequality_only=True)
		else:
			prefer_numeric = index == 0 or rng.random() < 0.6
			if prefer_numeric and any(col not in used for col in NUMERIC_COLUMNS):
				condition = _choose_numeric_condition(rng, df, used)
			else:
				condition = _choose_categorical_condition(rng, df, used)
		conditions.append(condition)
		used.add(condition["column"])
	return conditions


def _mask_from_conditions(df: pd.DataFrame, conditions: list[dict[str, Any]]) -> pd.Series:
	mask = pd.Series(True, index=df.index)
	for condition in conditions:
		mask &= _apply_condition(df, condition["column"], condition["operator"], condition["value"])
	return mask


def _choose_sort(rng: np.random.Generator, columns: list[str]) -> dict[str, Any]:
	sortable = [col for col in columns if col in SORTABLE_COLUMNS] or list(SORTABLE_COLUMNS)
	# Prefer last_name when available so alphabetized-name prompts show up often.
	if "last_name" in sortable and rng.random() < 0.55:
		column = "last_name"
		ascending = True
	else:
		column = str(rng.choice(sortable))
		ascending = bool(rng.choice([True, False])) if column != "last_name" else True
	return {"column": column, "ascending": ascending}


def _easy_summary_specs(df: pd.DataFrame) -> list[dict[str, Any]]:
	"""Build a large pool of single-variable summary prompts from the live frame."""
	specs: list[dict[str, Any]] = []

	for column in NUMERIC_COLUMNS:
		if column == "insurance":
			continue
		series = df[column]
		specs.extend(
			[
				{
					"prompt": f"What is the maximum {column} in the dataset?",
					"expected": int(series.max()),
					"column": column,
					"stat": "max",
				},
				{
					"prompt": f"What is the minimum {column} in the dataset?",
					"expected": int(series.min()),
					"column": column,
					"stat": "min",
				},
				{
					"prompt": f"What is the median {column} in the dataset?",
					"expected": float(series.median()),
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

	female_count = int((df["sex"] == "female").sum())
	male_count = int((df["sex"] == "male").sum())
	specs.extend(
		[
			{
				"prompt": "How many patients in the dataset are women (sex == 'female')?",
				"expected": female_count,
				"column": "sex",
				"stat": "count_value",
			},
			{
				"prompt": "How many patients in the dataset are men (sex == 'male')?",
				"expected": male_count,
				"column": "sex",
				"stat": "count_value",
			},
		]
	)

	for value in sorted(df["smoking_status"].unique()):
		specs.append(
			{
				"prompt": f"How many patients have smoking_status '{value}'?",
				"expected": int((df["smoking_status"] == value).sum()),
				"column": "smoking_status",
				"stat": "count_value",
			}
		)

	for value in sorted(df["department"].unique()):
		specs.append(
			{
				"prompt": f"How many patients are in the '{value}' department?",
				"expected": int((df["department"] == value).sum()),
				"column": "department",
				"stat": "count_value",
			}
		)

	insured = int((df["insurance"] == 1).sum())
	uninsured = int((df["insurance"] == 0).sum())
	specs.extend(
		[
			{
				"prompt": "How many patients have insurance (insurance == 1)?",
				"expected": insured,
				"column": "insurance",
				"stat": "count_value",
			},
			{
				"prompt": "How many patients do not have insurance (insurance == 0)?",
				"expected": uninsured,
				"column": "insurance",
				"stat": "count_value",
			},
		]
	)

	for column in ["sex", "smoking_status", "department", "last_name", "first_name"]:
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
				"prompt": "How many rows (patients) are in the dataset?",
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
			{
				"prompt": "What is the age of the oldest patient?",
				"expected": int(df["age"].max()),
				"column": "age",
				"stat": "max",
			},
			{
				"prompt": "What is the age of the youngest patient?",
				"expected": int(df["age"].min()),
				"column": "age",
				"stat": "min",
			},
			{
				"prompt": "What is the highest blood_pressure in the dataset?",
				"expected": int(df["blood_pressure"].max()),
				"column": "blood_pressure",
				"stat": "max",
			},
			{
				"prompt": "What is the lowest cholesterol in the dataset?",
				"expected": int(df["cholesterol"].min()),
				"column": "cholesterol",
				"stat": "min",
			},
		]
	)
	return specs


def _build_easy_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	specs = _easy_summary_specs(df)
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
	# One or two feature filters; return a focused column subset.
	condition_count = 1 if rng.random() < 0.7 else 2
	conditions = _choose_conditions(rng, df, condition_count)
	column_count = int(rng.integers(1, 4))  # 1–3 columns
	preferred: list[str] = []
	if rng.random() < 0.55:
		preferred.append(str(rng.choice(["first_name", "last_name", "age"])))
	remaining = [c for c in SELECTABLE_COLUMNS if c not in preferred]
	need = max(0, column_count - len(preferred))
	extra_cols = (
		list(rng.choice(remaining, size=min(need, len(remaining)), replace=False)) if need else []
	)
	chosen = set(preferred[:column_count] + list(extra_cols))
	columns = [c for c in SELECTABLE_COLUMNS if c in chosen][:column_count]
	if not columns:
		columns = _pick_columns(rng, count=2)

	working = df.loc[_mask_from_conditions(df, conditions), columns].copy().reset_index(drop=True)
	prompt = (
		f"Return a dataframe with the {_human_column_list(columns)} of all patients where "
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
	# Inequality filter(s) + multi-column result + sort.
	condition_count = 1 if rng.random() < 0.65 else 2
	conditions = _choose_conditions(rng, df, condition_count, require_inequality=True)
	column_count = int(rng.integers(2, 5))
	# Keep identity columns visible often for sorted patient lists.
	must_have = []
	if rng.random() < 0.75:
		must_have.append("last_name")
	if rng.random() < 0.45:
		must_have.append("first_name")
	if rng.random() < 0.55:
		must_have.append("age")
	remaining = [c for c in SELECTABLE_COLUMNS if c not in must_have]
	need = max(0, column_count - len(must_have))
	extra_cols = list(rng.choice(remaining, size=min(need, len(remaining)), replace=False)) if need else []
	columns = [c for c in SELECTABLE_COLUMNS if c in set(must_have + list(extra_cols))]
	if len(columns) < 2:
		columns = _pick_columns(rng, count=3)

	sort_spec = _choose_sort(rng, columns)
	if sort_spec["column"] not in columns:
		columns = [sort_spec["column"]] + [c for c in columns if c != sort_spec["column"]]
		columns = [c for c in SELECTABLE_COLUMNS if c in columns]

	working = df.loc[_mask_from_conditions(df, conditions), columns].copy()
	working = working.sort_values(
		sort_spec["column"],
		ascending=sort_spec["ascending"],
	).reset_index(drop=True)

	direction = "ascending" if sort_spec["ascending"] else "descending"
	if sort_spec["column"] == "last_name" and sort_spec["ascending"]:
		sort_phrase = "alphabetized by last_name"
	else:
		sort_phrase = f"sorted by {sort_spec['column']} in {direction} order"

	prompt = (
		f"Return a dataframe with the {_human_column_list(columns)} of all patients where "
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
	mode = (task or {}).get("mode") or "subset"
	if mode == "summary":
		return scalars_match(answer, task.get("expected"))
	return dataframes_match(df, task.get("expected_df"))
