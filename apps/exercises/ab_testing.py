from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from apps.exercises.content import render_prompt

ALPHA = 0.05


def student_t_sf(t_abs: float, df: float) -> float:
	"""Approximate two-sided Student-t p-value with a normal tail (adequate for n ≳ 40)."""
	del df  # retained for call-site compatibility with a full t distribution later
	if not np.isfinite(t_abs):
		return float("nan")
	z = abs(float(t_abs))
	return float(min(1.0, max(0.0, math.erfc(z / math.sqrt(2.0)))))


def welch_ttest(a: Any, b: Any) -> dict[str, float]:
	"""Welch's two-sample t-test. Returns t_statistic, df, and two-sided p_value."""
	left = np.asarray(a, dtype=float)
	right = np.asarray(b, dtype=float)
	left = left[np.isfinite(left)]
	right = right[np.isfinite(right)]
	n1 = left.size
	n2 = right.size
	if n1 < 2 or n2 < 2:
		raise ValueError("Each group needs at least 2 observations for a t-test.")

	mean1 = float(left.mean())
	mean2 = float(right.mean())
	var1 = float(left.var(ddof=1))
	var2 = float(right.var(ddof=1))
	denom = math.sqrt(var1 / n1 + var2 / n2)
	if denom == 0:
		t_stat = 0.0 if mean1 == mean2 else float("inf")
		df = float(n1 + n2 - 2)
		p_value = 1.0 if mean1 == mean2 else 0.0
		return {"t_statistic": t_stat, "df": df, "p_value": p_value}

	t_stat = (mean1 - mean2) / denom
	df_num = (var1 / n1 + var2 / n2) ** 2
	df_den = (var1 / n1) ** 2 / (n1 - 1) + (var2 / n2) ** 2 / (n2 - 1)
	df = float(df_num / df_den) if df_den else float(n1 + n2 - 2)
	p_value = student_t_sf(abs(t_stat), df)
	return {
		"t_statistic": float(t_stat),
		"df": df,
		"p_value": float(p_value),
	}


def _make_groups(
	rng: np.random.Generator,
	*,
	n: int,
	mean_a: float,
	mean_b: float,
	sd: float,
) -> tuple[np.ndarray, np.ndarray]:
	group_a = rng.normal(mean_a, sd, size=n)
	group_b = rng.normal(mean_b, sd, size=n)
	return group_a, group_b


def _groups_with_p_constraint(
	rng: np.random.Generator,
	*,
	want_significant: bool,
	p_low: float | None = None,
	p_high: float | None = None,
	n: int = 80,
) -> tuple[np.ndarray, np.ndarray, float]:
	"""Build two groups whose Welch p-value lands in the requested regime."""
	for _trial in range(16):
		sd = float(rng.uniform(1.4, 2.6))
		base_rng = np.random.default_rng(int(rng.integers(0, 1_000_000_000)))
		noise_a = base_rng.normal(0.0, sd, size=n)
		noise_b = base_rng.normal(0.0, sd, size=n)

		def groups_for_delta(delta: float) -> tuple[np.ndarray, np.ndarray, float]:
			group_a = noise_a
			group_b = noise_b + delta
			return group_a, group_b, welch_ttest(group_a, group_b)["p_value"]

		if want_significant:
			for delta in np.linspace(0.4, 2.8, 36):
				group_a, group_b, p_value = groups_for_delta(float(delta))
				if p_value < ALPHA:
					return group_a, group_b, p_value
			continue

		if p_low is not None and p_high is not None:
			low, high = 0.0, 2.2
			best = None
			for _ in range(32):
				mid = (low + high) / 2.0
				group_a, group_b, p_value = groups_for_delta(mid)
				best = (group_a, group_b, p_value)
				if p_low <= p_value <= p_high:
					return group_a, group_b, p_value
				if p_value > p_high:
					low = mid
				else:
					high = mid
			# Dense scan near the last bracket.
			for delta in np.linspace(max(0.0, low - 0.2), high + 0.2, 40):
				group_a, group_b, p_value = groups_for_delta(float(delta))
				if p_low <= p_value <= p_high:
					return group_a, group_b, p_value
			continue

		group_a, group_b, p_value = groups_for_delta(0.05)
		if p_value >= 0.10:
			return group_a, group_b, p_value

	# Absolute fallback: identical groups → clearly non-significant / not relevant.
	fallback = np.random.default_rng(123)
	group_a = fallback.normal(0.0, 1.5, size=n)
	group_b = group_a.copy() + (0.9 if want_significant else 0.0)
	if want_significant:
		group_b = group_a + 2.0
	return group_a, group_b, welch_ttest(group_a, group_b)["p_value"]

def _frame_from_groups(
	group_a: np.ndarray,
	group_b: np.ndarray,
	metric: str,
	*,
	seed: int = 42,
	data_field: str | None = None,
	dataset_file: str | None = None,
) -> pd.DataFrame:
	"""Compose an experiment table from zoo rows plus controlled A/B metrics."""
	from apps.exercises.data_zoo import sample_zoo_dataframe

	n = int(len(group_a) + len(group_b))
	sector = str(data_field or "marketing").strip().lower() or "marketing"
	zoo = sample_zoo_dataframe(
		sector,
		rows=n,
		seed=seed,
		dataset_file=(dataset_file or None),
	)
	frame = zoo.iloc[:n].copy().reset_index(drop=True)
	frame["variant"] = ["A"] * len(group_a) + ["B"] * len(group_b)
	frame[metric] = np.concatenate([group_a, group_b])
	return frame


def _build_easy_task(
	rng: np.random.Generator,
	*,
	seed: int,
	data_field: str | None = None,
	dataset_file: str | None = None,
) -> dict[str, Any]:
	want_significant = bool(rng.random() < 0.55)
	metric = str(rng.choice(["conversion_time_sec", "revenue", "session_minutes", "nps"]))
	group_a, group_b, p_value = _groups_with_p_constraint(
		rng,
		want_significant=want_significant,
		n=int(rng.integers(60, 121)),
	)
	different = bool(p_value < ALPHA)
	df = _frame_from_groups(
		group_a,
		group_b,
		metric,
		seed=seed,
		data_field=data_field,
		dataset_file=dataset_file,
	)
	label = "significantly different" if different else "not significantly different"
	prompt = render_prompt(
		"ab_testing",
		"ttest_decision",
		metric=metric,
		alpha=ALPHA,
	)
	return {
		"difficulty": "easy",
		"mode": "ttest_decision",
		"prompt": prompt,
		"metric": metric,
		"alpha": ALPHA,
		"expected": {
			"different": different,
			"p_value": p_value,
			"label": label,
		},
		"group_a": group_a,
		"group_b": group_b,
		"df": df,
	}


def _bayes_scenarios(rng: np.random.Generator) -> dict[str, Any]:
	scenarios = [
		{
			"title": "medical screening",
			"prior": 0.02,
			"sensitivity": 0.95,
			"false_positive": 0.08,
			"event": "disease",
			"evidence": "positive test",
		},
		{
			"title": "spam filter",
			"prior": 0.30,
			"sensitivity": 0.90,
			"false_positive": 0.05,
			"event": "spam",
			"evidence": "flagged message",
		},
		{
			"title": "fraud alert",
			"prior": 0.01,
			"sensitivity": 0.92,
			"false_positive": 0.04,
			"event": "fraud",
			"evidence": "alert triggered",
		},
		{
			"title": "churn model",
			"prior": 0.15,
			"sensitivity": 0.80,
			"false_positive": 0.10,
			"event": "churn",
			"evidence": "high-risk score",
		},
	]
	base = dict(scenarios[int(rng.integers(0, len(scenarios)))])
	# Mild jitter so repeats stay fresh but remain curriculum-friendly.
	base["prior"] = round(float(np.clip(base["prior"] * rng.uniform(0.8, 1.2), 0.005, 0.45)), 3)
	base["sensitivity"] = round(float(np.clip(base["sensitivity"] * rng.uniform(0.95, 1.02), 0.7, 0.99)), 3)
	base["false_positive"] = round(
		float(np.clip(base["false_positive"] * rng.uniform(0.8, 1.25), 0.01, 0.25)),
		3,
	)
	prior = base["prior"]
	likelihood = base["sensitivity"]
	false_positive = base["false_positive"]
	evidence = likelihood * prior + false_positive * (1.0 - prior)
	posterior = (likelihood * prior) / evidence
	base["posterior"] = float(posterior)
	base["evidence_prob"] = float(evidence)
	return base


def _build_medium_task(
	rng: np.random.Generator,
	*,
	seed: int,
	data_field: str | None = None,
	dataset_file: str | None = None,
) -> dict[str, Any]:
	from apps.exercises.data_zoo import sample_zoo_dataframe

	scenario = _bayes_scenarios(rng)
	prompt = render_prompt(
		"ab_testing",
		"bayes",
		title=scenario["title"],
		event=scenario["event"],
		evidence=scenario["evidence"],
		prior=scenario["prior"],
		sensitivity=scenario["sensitivity"],
		false_positive=scenario["false_positive"],
	)
	# Zoo-backed context table plus the Bayes quantities students need.
	sector = str(data_field or "marketing").strip().lower() or "marketing"
	zoo = sample_zoo_dataframe(
		sector,
		rows=24,
		seed=seed,
		dataset_file=(dataset_file or None),
	)
	df = zoo.copy()
	df["bayes_quantity"] = (
		["P(A)", "P(B|A)", "P(B|not A)"] + [""] * max(0, len(df) - 3)
	)[: len(df)]
	df["bayes_value"] = (
		[scenario["prior"], scenario["sensitivity"], scenario["false_positive"]]
		+ [float("nan")] * max(0, len(df) - 3)
	)[: len(df)]
	return {
		"difficulty": "medium",
		"mode": "bayes",
		"prompt": prompt,
		"scenario": scenario,
		"expected": {"answer": scenario["posterior"]},
		"group_a": None,
		"group_b": None,
		"df": df,
	}


def _build_hard_task(
	rng: np.random.Generator,
	*,
	seed: int,
	data_field: str | None = None,
	dataset_file: str | None = None,
) -> dict[str, Any]:
	metric = str(rng.choice(["lift_score", "retention_days", "basket_value", "latency_ms"]))
	group_a, group_b, p_value = _groups_with_p_constraint(
		rng,
		want_significant=False,
		p_low=0.11,
		p_high=0.40,
		n=int(rng.integers(70, 140)),
	)
	mean_diff = abs(float(group_a.mean() - group_b.mean()))
	pooled_sd = float(np.sqrt((group_a.var(ddof=1) + group_b.var(ddof=1)) / 2))
	effect_size = mean_diff / pooled_sd if pooled_sd else 0.0
	# With p in 0.11–0.40 the difference is not significant at α=0.05; treat as not relevant.
	relevant = False
	different = False
	df = _frame_from_groups(
		group_a,
		group_b,
		metric,
		seed=seed,
		data_field=data_field,
		dataset_file=dataset_file,
	)
	prompt = render_prompt(
		"ab_testing",
		"ttest_relevance",
		metric=metric,
		alpha=ALPHA,
	)
	return {
		"difficulty": "hard",
		"mode": "ttest_relevance",
		"prompt": prompt,
		"metric": metric,
		"alpha": ALPHA,
		"expected": {
			"different": different,
			"relevant": relevant,
			"p_value": p_value,
			"effect_size": effect_size,
			"mean_diff": mean_diff,
		},
		"group_a": group_a,
		"group_b": group_b,
		"df": df,
	}


def prepare_ab_testing(
	difficulty: str = "easy",
	seed: int = 42,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> dict[str, Any]:
	"""Build A/B and Bayes tasks with pre-split groups where needed."""
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		raise ValueError("Unknown difficulty. Use easy, medium, or hard.")

	rng = np.random.default_rng(seed)
	sector = data_field or topic
	builders = {
		"easy": _build_easy_task,
		"medium": _build_medium_task,
		"hard": _build_hard_task,
	}
	task = builders[difficulty_key](
		rng,
		seed=seed,
		data_field=sector,
		dataset_file=dataset_file,
	)
	payload = {
		"df": task.pop("df"),
		"group_a": task.pop("group_a"),
		"group_b": task.pop("group_b"),
		"task": task,
		"different": None,
		"relevant": None,
		"answer": None,
		"p_value": None,
	}
	return payload


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


def _close(actual: Any, expected: float, tol: float = 1e-3) -> bool:
	try:
		return abs(float(actual) - float(expected)) <= tol
	except (TypeError, ValueError):
		return False


def ab_testing_passes(
	task: dict[str, Any] | None,
	*,
	different: Any = None,
	relevant: Any = None,
	answer: Any = None,
	p_value: Any = None,
) -> bool:
	"""Validate student decisions / Bayes posterior for the generated task."""
	task = task or {}
	mode = task.get("mode")
	expected = task.get("expected") or {}

	if mode == "bayes":
		return _close(answer, expected["answer"], tol=5e-3)

	if mode == "ttest_decision":
		decision = _boolish(different)
		if decision is None or decision != bool(expected["different"]):
			return False
		# p_value is required and should be in the same reject/fail-to-reject region.
		try:
			p = float(p_value)
		except (TypeError, ValueError):
			return False
		if not (0.0 <= p <= 1.0):
			return False
		return (p < ALPHA) == bool(expected["different"])

	if mode == "ttest_relevance":
		decision = _boolish(different)
		relevance = _boolish(relevant)
		if decision is None or relevance is None:
			return False
		if decision != bool(expected["different"]):
			return False
		if relevance != bool(expected["relevant"]):
			return False
		try:
			p = float(p_value)
		except (TypeError, ValueError):
			return False
		if not (0.0 <= p <= 1.0):
			return False
		# Accept student p-values in the designed “close call” band (or nearby).
		return 0.05 <= p <= 0.50

	return False
