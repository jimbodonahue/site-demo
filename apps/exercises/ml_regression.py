"""ML Exercise 2: Regression strategies — linear, polynomial, decision tree."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_percentage_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import MinMaxScaler, PolynomialFeatures, StandardScaler
from sklearn.tree import DecisionTreeRegressor

from apps.exercises.content import render_prompt
from apps.exercises.ml_common import (
	build_ml_dataframe,
	close_metric,
	feature_matrix,
	name_match,
	pick_regression_target,
)


def _score(y_true, y_pred, metric: str) -> float:
	if metric == "rmse":
		return float(np.sqrt(mean_squared_error(y_true, y_pred)))
	if metric == "mape":
		# Avoid divide-by-zero blowups on near-zero targets.
		y_true = np.asarray(y_true, dtype=float)
		y_pred = np.asarray(y_pred, dtype=float)
		mask = np.abs(y_true) > 1e-6
		if mask.sum() == 0:
			return float("nan")
		return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))
	return float(r2_score(y_true, y_pred))


def _better(metric: str, a: float, b: float) -> str:
	"""Return 'a' or 'b' for which score is better given the metric."""
	if metric == "r2":
		return "a" if a >= b else "b"
	return "a" if a <= b else "b"


def _build_easy(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_regression_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=seed)
	lin = LinearRegression().fit(X_train, y_train)
	tree = DecisionTreeRegressor(max_depth=4, random_state=seed).fit(X_train, y_train)
	lin_r2 = _score(y_test, lin.predict(X_test), "r2")
	tree_r2 = _score(y_test, tree.predict(X_test), "r2")
	winner = "linear" if lin_r2 >= tree_r2 else "tree"
	prompt = render_prompt(
		"ml_regression",
		"easy",
		target=target,
		default=(
			f"Using the pre-split arrays for target `{target}`, train a linear regression and a "
			"decision tree (max_depth=4, random_state from the task seed) on the training set, "
			"score both on the test set with R², and set `answer['best_model']` to "
			"`'linear'` or `'tree'`. Also store `answer['linear_r2']` and `answer['tree_r2']` "
			"(rounded to 4 decimals)."
		),
	)
	return {
		"mode": "compare_two",
		"prompt": prompt,
		"target": target,
		"seed": seed,
		"expected": {
			"best_model": winner,
			"linear_r2": round(lin_r2, 4),
			"tree_r2": round(tree_r2, 4),
		},
		"X_train": X_train,
		"X_test": X_test,
		"y_train": y_train,
		"y_test": y_test,
	}


def _build_medium(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_regression_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	family = str(rng.choice(["polynomial", "tree"]))
	X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=seed)
	if family == "polynomial":
		scores = {}
		for degree in range(1, 5):
			model = make_pipeline(PolynomialFeatures(degree, include_bias=False), LinearRegression())
			model.fit(X_train, y_train)
			scores[degree] = _score(y_test, model.predict(X_test), "r2")
		best = max(scores, key=scores.get)
		expected = {"family": "polynomial", "best_param": int(best), "best_r2": round(scores[best], 4)}
		prompt = render_prompt(
			"ml_regression",
			"medium_poly",
			target=target,
			default=(
				f"Split `df` with target `{target}` (test_size=0.25, random_state={seed}). "
				"Fit polynomial regressions of degree 1..4 on the training set and pick the best "
				"test R². Store `answer['family']='polynomial'`, `answer['best_param']` (degree), "
				"and `answer['best_r2']` (4 decimals)."
			),
		)
	else:
		scores = {}
		for depth in range(3, 9):
			model = DecisionTreeRegressor(max_depth=depth, random_state=seed).fit(X_train, y_train)
			scores[depth] = _score(y_test, model.predict(X_test), "r2")
		best = max(scores, key=scores.get)
		expected = {"family": "tree", "best_param": int(best), "best_r2": round(scores[best], 4)}
		prompt = render_prompt(
			"ml_regression",
			"medium_tree",
			target=target,
			default=(
				f"Split `df` with target `{target}` (test_size=0.25, random_state={seed}). "
				"Fit decision trees with max_depth 3..8 and pick the best test R². "
				"Store `answer['family']='tree'`, `answer['best_param']` (depth), "
				"and `answer['best_r2']` (4 decimals)."
			),
		)
	return {
		"mode": "tune_one",
		"prompt": prompt,
		"target": target,
		"seed": seed,
		"family": family,
		"expected": expected,
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def _build_hard(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_regression_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	scaler_name = str(rng.choice(["standard", "minmax"]))
	family = str(rng.choice(["polynomial", "tree"]))
	metric = str(rng.choice(["r2", "rmse", "mape"]))
	X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=seed)
	scaler = StandardScaler() if scaler_name == "standard" else MinMaxScaler()
	X_train_s = scaler.fit_transform(X_train)
	X_test_s = scaler.transform(X_test)
	if family == "polynomial":
		degree = int(rng.integers(1, 5))
		model = make_pipeline(PolynomialFeatures(degree, include_bias=False), LinearRegression())
		model.fit(X_train_s, y_train)
		score = _score(y_test, model.predict(X_test_s), metric)
		param = degree
	else:
		depth = int(rng.integers(3, 9))
		model = DecisionTreeRegressor(max_depth=depth, random_state=seed).fit(X_train_s, y_train)
		score = _score(y_test, model.predict(X_test_s), metric)
		param = depth
	prompt = render_prompt(
		"ml_regression",
		"hard",
		target=target,
		scaler=scaler_name,
		family=family,
		param=param,
		metric=metric,
		default=(
			f"Split `df` (target `{target}`, test_size=0.25, random_state={seed}), "
			f"scale with a {scaler_name} scaler, then fit a {family} model with "
			f"{'degree' if family == 'polynomial' else 'max_depth'}={param}. "
			f"Report `answer['metric']='{metric}'`, `answer['score']` (4 decimals), "
			f"`answer['family']='{family}'`, and `answer['param']={param}`."
		),
	)
	return {
		"mode": "scaled_chosen",
		"prompt": prompt,
		"target": target,
		"seed": seed,
		"expected": {
			"metric": metric,
			"score": round(float(score), 4),
			"family": family,
			"param": int(param),
			"scaler": scaler_name,
		},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def prepare_ml_regression(
	difficulty: str = "easy",
	seed: int = 42,
	rows: int = 100,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> dict[str, Any]:
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		difficulty_key = "easy"
	rng = np.random.default_rng(seed)
	df = build_ml_dataframe(
		rows=rows, seed=seed, data_field=data_field, dataset_file=dataset_file, topic=topic
	)
	payload = {"easy": _build_easy, "medium": _build_medium, "hard": _build_hard}[difficulty_key](
		df, rng, seed
	)
	task = {
		"difficulty": difficulty_key,
		"mode": payload["mode"],
		"prompt": payload["prompt"],
		"target": payload["target"],
		"seed": seed,
		"expected": payload["expected"],
		"family": payload.get("family"),
	}
	return {
		"df": df,
		"task": task,
		"X_train": payload.get("X_train"),
		"X_test": payload.get("X_test"),
		"y_train": payload.get("y_train"),
		"y_test": payload.get("y_test"),
		"answer": None,
		"plotted": None,
	}


def ml_regression_passes(task: dict[str, Any] | None, *, answer: Any = None, plotted: Any = None) -> bool:
	del plotted
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False
	mode = task.get("mode")
	if mode == "compare_two":
		return (
			name_match(answer.get("best_model"), expected["best_model"])
			and close_metric(answer.get("linear_r2"), expected["linear_r2"], tol=0.05)
			and close_metric(answer.get("tree_r2"), expected["tree_r2"], tol=0.05)
		)
	if mode == "tune_one":
		return (
			name_match(answer.get("family"), expected["family"])
			and int(answer.get("best_param")) == int(expected["best_param"])
			and close_metric(answer.get("best_r2"), expected["best_r2"], tol=0.05)
		)
	if mode == "scaled_chosen":
		return (
			name_match(answer.get("metric"), expected["metric"])
			and name_match(answer.get("family"), expected["family"])
			and int(answer.get("param")) == int(expected["param"])
			and close_metric(answer.get("score"), expected["score"], tol=0.08)
		)
	return False
