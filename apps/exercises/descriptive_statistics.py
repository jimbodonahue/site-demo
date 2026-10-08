from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from apps.exercises.content import render_prompt

REGIONS = ["north", "south", "east", "west"]
SEGMENTS = ["consumer", "corporate", "small_business"]
PLANS = ["basic", "plus", "premium"]

FLOAT_COLUMNS = ["income", "satisfaction", "spend"]
INT_COLUMNS = ["age", "visits"]
CATEGORICAL_COLUMNS = ["region", "segment", "plan"]
CONTINUOUS_COLUMNS = FLOAT_COLUMNS + ["age"]  # age treated as continuous for groupby


def build_survey_dataframe(
	rows: int = 120,
	seed: int = 42,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> pd.DataFrame:
	"""Build a survey-style table from a Data Zoo sample.

	Maps zoo columns onto the teaching schema (region/segment/plan/age/visits/
	income/spend/satisfaction) when possible so existing tasks keep working.
	"""
	from apps.exercises.data_zoo import sample_zoo_dataframe

	sector = str(data_field or topic or "marketing").strip().lower() or "marketing"
	zoo = sample_zoo_dataframe(
		sector,
		rows=max(60, int(rows)),
		seed=seed,
		dataset_file=(dataset_file or None),
	)
	rng = np.random.default_rng(seed)
	n = len(zoo)

	def _num(*candidates: str, fallback: np.ndarray) -> np.ndarray:
		for name in candidates:
			if name in zoo.columns and pd.api.types.is_numeric_dtype(zoo[name]):
				series = pd.to_numeric(zoo[name], errors="coerce")
				if series.notna().mean() >= 0.5:
					return series.fillna(series.median()).to_numpy(dtype=float)
		return fallback

	def _cat(*candidates: str, choices: list[str]) -> np.ndarray:
		for name in candidates:
			if name in zoo.columns:
				series = zoo[name].astype(str).fillna(choices[0])
				top = series.value_counts().head(len(choices)).index.tolist()
				if len(top) >= 2:
					# Relabel to the fixed teaching vocabulary when cardinalities match.
					mapping = {old: choices[index % len(choices)] for index, old in enumerate(top)}
					return series.map(mapping).fillna(choices[0]).to_numpy()
		return rng.choice(choices, size=n)

	age = _num("age", "admission_age", fallback=rng.integers(18, 75, size=n).astype(float))
	visits = _num(
		"email_clicks",
		"visits",
		"previous",
		"campaign",
		fallback=rng.integers(0, 12, size=n).astype(float),
	)
	income_fallback = 42_000 + age * 380 + rng.lognormal(0.0, 0.28, size=n) * 8_000
	income = _num(
		"annual_income",
		"income",
		"purchase_value",
		"balance",
		"charges",
		fallback=income_fallback,
	)
	spend = _num(
		"campaign_spend",
		"spend",
		"payment_value",
		"medication_cost",
		fallback=income * rng.uniform(0.04, 0.18, size=n),
	)
	satisfaction = _num(
		"conversion_rate",
		"loyalty_score",
		"satisfaction",
		"job_satisfaction",
		fallback=rng.normal(6.8, 1.4, size=n),
	)
	# Scale 0–1 scores into a ~1–10 satisfaction range.
	if float(np.nanmax(satisfaction)) <= 1.5:
		satisfaction = 1.0 + 9.0 * np.clip(satisfaction, 0, 1)

	return pd.DataFrame(
		{
			"region": _cat("region", "channel", choices=REGIONS),
			"segment": _cat("segment", "job", "education", choices=SEGMENTS),
			"plan": _cat("poutcome", "contact", "housing", choices=PLANS),
			"age": np.clip(age, 18, 90).astype(int),
			"visits": np.clip(visits, 0, None).astype(int),
			"income": np.round(np.clip(income, 1_000, None), 2),
			"spend": np.round(np.clip(spend, 0, None), 2),
			"satisfaction": np.round(np.clip(satisfaction, 1.0, 10.0), 2),
		}
	)


def _round2(value: float) -> float:
	return round(float(value), 2)


def _series_mode(series: pd.Series) -> Any:
	modes = series.mode(dropna=True)
	if modes.empty:
		return None
	return modes.iloc[0]


def _stat_value(series: pd.Series, stat: str) -> Any:
	if stat == "mean":
		return _round2(series.mean())
	if stat == "median":
		return _round2(series.median())
	if stat == "mode":
		value = _series_mode(series)
		if isinstance(value, (np.floating, float)):
			return _round2(value)
		if isinstance(value, (np.integer, int)):
			return int(value)
		return value
	if stat == "std":
		return _round2(series.std(ddof=1))
	if stat == "var":
		return _round2(series.var(ddof=1))
	raise ValueError(f"Unknown stat: {stat}")


def _build_easy_within_variable_questions(
	df: pd.DataFrame,
	rng: np.random.Generator,
	n_questions: int,
) -> list[dict[str, Any]]:
	"""Compare mean/median/mode on one variable (mode only if not float)."""
	int_cols = [c for c in INT_COLUMNS if c in df.columns]
	float_cols = [c for c in FLOAT_COLUMNS if c in df.columns]
	cat_cols = [c for c in CATEGORICAL_COLUMNS if c in df.columns]

	use_categorical = bool(rng.random() < 0.35 and cat_cols)
	if use_categorical:
		column = str(rng.choice(cat_cols))
		stats = ["mode"]
		# Pad with count-style companions from a related numeric if needed.
		numeric = str(rng.choice(int_cols + float_cols))
		while len(stats) < n_questions:
			stats.append(str(rng.choice(["mean", "median", "std", "var"])))
		questions: list[dict[str, Any]] = []
		# First question is always mode of the categorical.
		questions.append(
			{
				"text": render_prompt(
					"descriptive_statistics",
					"mode_categorical",
					column=column,
				),
				"expected": _stat_value(df[column], "mode"),
				"kind": "scalar",
			}
		)
		for stat in stats[1 : n_questions]:
			label = {
				"mean": "mean",
				"median": "median",
				"std": "standard deviation",
				"var": "variance",
			}[stat]
			questions.append(
				{
					"text": render_prompt(
						"descriptive_statistics",
						"stat_of_column",
						label=label,
						column=numeric,
					),
					"expected": _stat_value(df[numeric], stat),
					"kind": "scalar",
				}
			)
		return questions

	# Prefer an integer column so mode is allowed alongside mean/median.
	prefer_int = bool(rng.random() < 0.65 and int_cols)
	column = str(rng.choice(int_cols if prefer_int else (int_cols + float_cols)))
	is_float = column in float_cols
	allowed = ["mean", "median"] if is_float else ["mean", "median", "mode"]
	# Always include at least mean and median for within-variable comparison.
	chosen = ["mean", "median"]
	if "mode" in allowed and rng.random() < 0.8:
		chosen.append("mode")
	while len(chosen) < n_questions:
		extra = str(rng.choice(["std", "var"]))
		if extra not in chosen:
			chosen.append(extra)
		else:
			break
	chosen = chosen[:n_questions]

	questions = []
	for stat in chosen:
		label = {
			"mean": "mean",
			"median": "median",
			"mode": "mode (most frequent value)",
			"std": "standard deviation",
			"var": "variance",
		}[stat]
		key = "stat_of_column_no_round" if stat == "mode" else "stat_of_column"
		questions.append(
			{
				"text": render_prompt(
					"descriptive_statistics",
					key,
					label=label,
					column=column,
				),
				"expected": _stat_value(df[column], stat),
				"kind": "scalar",
			}
		)
	return questions


def _build_easy_between_variable_questions(
	df: pd.DataFrame,
	rng: np.random.Generator,
	n_questions: int,
) -> list[dict[str, Any]]:
	"""Compare SD/variance across variables, with optional other stats."""
	numeric = [c for c in FLOAT_COLUMNS + INT_COLUMNS if c in df.columns]
	left, right = [str(x) for x in rng.choice(numeric, size=2, replace=False)]
	std_left = float(df[left].std(ddof=1))
	std_right = float(df[right].std(ddof=1))
	higher_std = left if std_left >= std_right else right
	var_target = str(rng.choice([left, right]))

	questions: list[dict[str, Any]] = [
		{
			"text": render_prompt(
				"descriptive_statistics",
				"which_larger_std",
				left=left,
				right=right,
			),
			"expected": higher_std,
			"kind": "name",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"stat_of_column",
				label="sample variance",
				column=var_target,
			),
			"expected": _stat_value(df[var_target], "var"),
			"kind": "scalar",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"stat_of_column",
				label="sample standard deviation",
				column=left,
			),
			"expected": _stat_value(df[left], "std"),
			"kind": "scalar",
		},
	]

	other = left if var_target == right else right
	remaining_pool = [
		{
			"text": render_prompt(
				"descriptive_statistics",
				"stat_of_column",
				label="mean",
				column=right,
			),
			"expected": _stat_value(df[right], "mean"),
			"kind": "scalar",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"stat_of_column",
				label="median",
				column=left,
			),
			"expected": _stat_value(df[left], "median"),
			"kind": "scalar",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"stat_of_column",
				label="sample variance",
				column=other,
			),
			"expected": _stat_value(df[other], "var"),
			"kind": "scalar",
		},
	]
	rng.shuffle(remaining_pool)
	while len(questions) < n_questions and remaining_pool:
		questions.append(remaining_pool.pop())
	return questions[:n_questions]


def _format_questions(questions: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
	lines = []
	expected: dict[str, Any] = {}
	for index, question in enumerate(questions, start=1):
		key = f"q{index}"
		lines.append(
			render_prompt(
				"descriptive_statistics",
				"question_line",
				index=index,
				text=question["text"],
				answer_key=key,
			)
		)
		expected[key] = question["expected"]
	keys = ", ".join(f"'q{i}'" for i in range(1, len(questions) + 1))
	prompt = render_prompt(
		"descriptive_statistics",
		"batch_intro",
		keys=keys,
		lines="\n".join(lines),
	)
	return prompt, expected


def _build_easy_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	n_questions = int(rng.integers(3, 6))  # 3–5
	if rng.random() < 0.55:
		questions = _build_easy_within_variable_questions(df, rng, n_questions)
		family = "within_variable"
	else:
		questions = _build_easy_between_variable_questions(df, rng, n_questions)
		family = "between_variables"
	prompt, expected = _format_questions(questions)
	return {
		"difficulty": "easy",
		"mode": "summary_batch",
		"family": family,
		"prompt": prompt,
		"expected": expected,
		"requires_plot": False,
	}


def _build_medium_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	"""Group-by comparisons of continuous measures by a discrete factor."""
	group_col = str(rng.choice(CATEGORICAL_COLUMNS))
	value_col = str(rng.choice(["income", "spend", "satisfaction", "age"]))
	n_questions = int(rng.integers(3, 6))

	grouped = df.groupby(group_col, observed=True)[value_col]
	means = grouped.mean()
	medians = grouped.median()
	stds = grouped.std(ddof=1)
	highest_mean_group = str(means.idxmax())
	lowest_mean_group = str(means.idxmin())
	skew_gap = (means - medians).abs()
	skew_group = str(skew_gap.idxmax())
	highest_std_group = str(stds.idxmax())

	required = [
		{
			"text": render_prompt(
				"descriptive_statistics",
				"groupby_highest_mean",
				group_col=group_col,
				value_col=value_col,
			),
			"expected": highest_mean_group,
			"kind": "name",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"groupby_skew_gap",
				group_col=group_col,
				value_col=value_col,
			),
			"expected": skew_group,
			"kind": "name",
		},
	]
	extras = [
		{
			"text": render_prompt(
				"descriptive_statistics",
				"groupby_mean_value",
				value_col=value_col,
				group_col=group_col,
				group=highest_mean_group,
			),
			"expected": _round2(means.loc[highest_mean_group]),
			"kind": "scalar",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"groupby_lowest_mean",
				group_col=group_col,
				value_col=value_col,
			),
			"expected": lowest_mean_group,
			"kind": "name",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"groupby_highest_std",
				group_col=group_col,
				value_col=value_col,
			),
			"expected": highest_std_group,
			"kind": "name",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"groupby_median_value",
				value_col=value_col,
				group_col=group_col,
				group=skew_group,
			),
			"expected": _round2(medians.loc[skew_group]),
			"kind": "scalar",
		},
	]
	rng.shuffle(extras)
	questions = (required + extras)[:n_questions]
	prompt_header = render_prompt(
		"descriptive_statistics",
		"groupby_header",
		group_col=group_col,
		value_col=value_col,
	)
	prompt, expected = _format_questions(questions)
	return {
		"difficulty": "medium",
		"mode": "groupby_compare",
		"prompt": prompt_header + prompt,
		"expected": expected,
		"group_col": group_col,
		"value_col": value_col,
		"requires_plot": False,
	}


def _inject_bimodal_column(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, str, list[float]]:
	"""Add a clearly bimodal continuous column."""
	n = len(df)
	col = "wait_minutes"
	centers = [22.0, 78.0]
	# Slight jitter of centers so seeds differ but stay separable.
	centers = [c + float(rng.uniform(-2.0, 2.0)) for c in centers]
	mask = rng.random(n) < 0.52
	values = np.empty(n, dtype=float)
	values[mask] = rng.normal(centers[0], 3.2, size=int(mask.sum()))
	values[~mask] = rng.normal(centers[1], 3.2, size=int((~mask).sum()))
	out = df.copy()
	out[col] = np.round(values, 2)
	return out, col, [float(centers[0]), float(centers[1])]


def _inject_correlated_columns(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, str, str, float]:
	"""Add two strongly correlated continuous columns."""
	n = len(df)
	left = "metric_x"
	right = "metric_y"
	x = rng.normal(50.0, 10.0, size=n)
	noise = rng.normal(0.0, 2.5, size=n)
	y = 1.7 * x + 5.0 + noise
	out = df.copy()
	out[left] = np.round(x, 2)
	out[right] = np.round(y, 2)
	corr = float(pd.Series(x).corr(pd.Series(y)))
	return out, left, right, corr


def _build_hard_bimodal_task(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict[str, Any]]:
	frame, column, centers = _inject_bimodal_column(df, rng)
	# Continuous mode via rounding to nearest integer.
	rounded_mode = int(frame[column].round().mode().iloc[0])
	approx_modes = sorted(int(round(c)) for c in centers)
	n_questions = int(rng.integers(3, 5))
	questions = [
		{
			"text": render_prompt(
				"descriptive_statistics",
				"hard_bimodal_plot",
				column=column,
			),
			"expected": True,
			"kind": "plot_flag",
			"key": "plotted_ack",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"hard_bimodal_mode",
				column=column,
			),
			"expected": rounded_mode,
			"kind": "scalar",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"hard_bimodal_peaks",
				column=column,
			),
			"expected": approx_modes,
			"kind": "mode_pair",
		},
	]
	if n_questions >= 4:
		questions.append(
			{
				"text": render_prompt(
					"descriptive_statistics",
					"hard_bimodal_median",
					column=column,
				),
				"expected": _round2(frame[column].median()),
				"kind": "scalar",
			}
		)

	# Custom prompt wiring because one item is the plotted flag outside answer.
	answer_questions = [q for q in questions if q["kind"] != "plot_flag"]
	lines = [
		render_prompt(
			"descriptive_statistics",
			"hard_bimodal_plot_line",
			column=column,
		)
	]
	expected: dict[str, Any] = {}
	for index, question in enumerate(answer_questions, start=1):
		key = f"q{index}"
		lines.append(
			render_prompt(
				"descriptive_statistics",
				"question_line",
				index=index + 1,
				text=question["text"],
				answer_key=key,
			)
		)
		expected[key] = question["expected"]
	prompt = render_prompt(
		"descriptive_statistics",
		"hard_bimodal_header",
		lines="\n".join(lines),
	)
	task = {
		"difficulty": "hard",
		"mode": "bimodal_hist",
		"prompt": prompt,
		"expected": expected,
		"requires_plot": True,
		"bimodal_column": column,
		"approx_mode_tol": 6,
	}
	return frame, task


def _build_hard_correlation_task(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict[str, Any]]:
	frame, left, right, corr = _inject_correlated_columns(df, rng)
	numeric_cols = [c for c in frame.select_dtypes(include=[np.number]).columns]
	corr_matrix = frame[numeric_cols].corr()
	# Strongest absolute off-diagonal pair.
	best_pair = (left, right)
	best_abs = 0.0
	for i, a in enumerate(numeric_cols):
		for b in numeric_cols[i + 1 :]:
			value = abs(float(corr_matrix.loc[a, b]))
			if value > best_abs:
				best_abs = value
				best_pair = (str(a), str(b))

	pair_sorted = tuple(sorted(best_pair))
	questions = [
		{
			"text": render_prompt("descriptive_statistics", "hard_corr_plot"),
			"kind": "plot_flag",
		},
		{
			"text": render_prompt("descriptive_statistics", "hard_corr_pair"),
			"expected": list(pair_sorted),
			"kind": "name_pair",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"hard_corr_value",
				left=left,
				right=right,
			),
			"expected": _round2(corr),
			"kind": "scalar",
		},
		{
			"text": render_prompt(
				"descriptive_statistics",
				"hard_corr_positive",
				left=left,
				right=right,
			),
			"expected": bool(corr > 0),
			"kind": "bool",
		},
	]
	n_questions = int(rng.integers(3, 5))
	answer_questions = [q for q in questions if q["kind"] != "plot_flag"][: n_questions - 1]
	# Always keep strongest pair + correlation value when possible.
	lines = [render_prompt("descriptive_statistics", "hard_corr_plot_line")]
	expected: dict[str, Any] = {}
	for index, question in enumerate(answer_questions, start=1):
		key = f"q{index}"
		lines.append(
			render_prompt(
				"descriptive_statistics",
				"question_line",
				index=index + 1,
				text=question["text"],
				answer_key=key,
			)
		)
		expected[key] = question["expected"]
	prompt = render_prompt(
		"descriptive_statistics",
		"hard_corr_header",
		lines="\n".join(lines),
	)
	task = {
		"difficulty": "hard",
		"mode": "correlation_heatmap",
		"prompt": prompt,
		"expected": expected,
		"requires_plot": True,
		"corr_pair": list(pair_sorted),
	}
	return frame, task


def _build_hard_task(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, dict[str, Any]]:
	if rng.random() < 0.5:
		return _build_hard_bimodal_task(df, rng)
	return _build_hard_correlation_task(df, rng)


def prepare_descriptive_statistics(
	difficulty: str = "easy",
	seed: int = 42,
	rows: int = 120,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> dict[str, Any]:
	"""Build descriptive-statistics tasks with a seeded survey dataframe."""
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		raise ValueError("Unknown difficulty. Use easy, medium, or hard.")

	rng = np.random.default_rng(seed)
	df = build_survey_dataframe(
		rows=rows,
		seed=seed,
		data_field=data_field,
		dataset_file=dataset_file,
		topic=topic,
	)

	if difficulty_key == "easy":
		task = _build_easy_task(df, rng)
	elif difficulty_key == "medium":
		task = _build_medium_task(df, rng)
	else:
		df, task = _build_hard_task(df, rng)

	return {
		"df": df,
		"task": task,
		"answer": None,
		"plotted": None,
	}


def _close(actual: Any, expected: float, tol: float = 0.02) -> bool:
	try:
		return abs(float(actual) - float(expected)) <= tol
	except (TypeError, ValueError):
		return False


def _name_match(actual: Any, expected: str) -> bool:
	if actual is None:
		return False
	return str(actual).strip().lower() == str(expected).strip().lower()


def _boolish(value: Any) -> bool | None:
	if isinstance(value, (bool, np.bool_)):
		return bool(value)
	if isinstance(value, (int, np.integer)) and value in (0, 1):
		return bool(value)
	if isinstance(value, str):
		lower = value.strip().lower()
		if lower in {"true", "yes", "y", "1"}:
			return True
		if lower in {"false", "no", "n", "0"}:
			return False
	return None


def _list_names_match(actual: Any, expected: list[str]) -> bool:
	if not isinstance(actual, (list, tuple)):
		return False
	if len(actual) != len(expected):
		return False
	left = sorted(str(item).strip().lower() for item in actual)
	right = sorted(str(item).strip().lower() for item in expected)
	return left == right


def _mode_pair_match(actual: Any, expected: list[int], tol: int = 6) -> bool:
	if not isinstance(actual, (list, tuple)) or len(actual) != 2:
		return False
	try:
		got = sorted(int(round(float(x))) for x in actual)
		want = sorted(int(x) for x in expected)
	except (TypeError, ValueError):
		return False
	return all(abs(a - b) <= tol for a, b in zip(got, want))


def _match_answer_value(actual: Any, expected: Any, *, mode: str, task: dict[str, Any]) -> bool:
	if isinstance(expected, bool) or type(expected) is bool:
		got = _boolish(actual)
		return got is not None and got == bool(expected)
	if isinstance(expected, str):
		return _name_match(actual, expected)
	if isinstance(expected, list) and expected and isinstance(expected[0], str):
		return _list_names_match(actual, expected)
	if isinstance(expected, list) and expected and isinstance(expected[0], (int, np.integer)):
		tol = int(task.get("approx_mode_tol") or 6)
		return _mode_pair_match(actual, list(expected), tol=tol)
	if isinstance(expected, (int, np.integer)) and not isinstance(expected, (bool, np.bool_)):
		try:
			return int(round(float(actual))) == int(expected)
		except (TypeError, ValueError):
			return False
	if isinstance(expected, (float, np.floating)):
		return _close(actual, float(expected), tol=0.05)
	return actual == expected


def descriptive_statistics_passes(
	task: dict[str, Any] | None,
	*,
	answer: Any = None,
	plotted: Any = None,
) -> bool:
	"""Validate the answer dict (and plot flag on hard tasks)."""
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False

	for key, expected_value in expected.items():
		if key not in answer:
			return False
		if not _match_answer_value(answer.get(key), expected_value, mode=task.get("mode") or "", task=task):
			return False

	if task.get("requires_plot"):
		flag = _boolish(plotted)
		if flag is not True:
			return False

	return True
