"""ML Exercise 3: Intro to classification."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, f1_score, precision_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from apps.exercises.content import render_prompt
from apps.exercises.ml_common import (
	build_ml_dataframe,
	close_metric,
	feature_matrix,
	name_match,
	pick_classification_target,
)


def _metric_score(y_true, y_pred, metric: str) -> float:
	average = "binary" if len(np.unique(y_true)) <= 2 else "macro"
	if metric == "precision":
		return float(precision_score(y_true, y_pred, average=average, zero_division=0))
	if metric == "f1":
		return float(f1_score(y_true, y_pred, average=average, zero_division=0))
	return float(accuracy_score(y_true, y_pred))


def _prepare_y(y: pd.Series) -> pd.Series:
	if y.nunique() > 6:
		# Median split into binary classes.
		return (y >= y.median()).astype(int)
	if not pd.api.types.is_integer_dtype(y):
		return pd.Series(pd.Categorical(y).codes, index=y.index).astype(int)
	return y.astype(int)


def _build_easy(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	y = _prepare_y(y)
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=y if y.nunique() > 1 else None
	)
	models = {
		"tree": DecisionTreeClassifier(max_depth=4, random_state=seed),
		# lbfgs (the default) handles multiclass targets; liblinear raises on
		# three or more classes, which the zoo targets regularly produce.
		"logreg": LogisticRegression(max_iter=500, random_state=seed),
		"svm": SVC(kernel="rbf", random_state=seed),
	}
	scores = {}
	for name, model in models.items():
		model.fit(X_train, y_train)
		scores[name] = _metric_score(y_test, model.predict(X_test), "accuracy")
	winner = max(scores, key=scores.get)
	prompt = render_prompt(
		"ml_classification",
		"easy",
		target=target,
		default=(
			f"Using the pre-split arrays for target `{target}`, train a decision tree "
			"(max_depth=4), logistic regression (max_iter=500), and an RBF SVM. "
			"Compare test accuracy and set `answer['best_model']` to `'tree'`, `'logreg'`, or `'svm'`. "
			"Also store `answer['scores']` as a dict of the three accuracies (4 decimals)."
		),
	)
	return {
		"mode": "compare_three",
		"prompt": prompt,
		"target": target,
		"expected": {
			"best_model": winner,
			"scores": {k: round(v, 4) for k, v in scores.items()},
		},
		"X_train": X_train,
		"X_test": X_test,
		"y_train": y_train,
		"y_test": y_test,
	}


def _build_medium(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	y = _prepare_y(y)
	family = str(rng.choice(["tree", "logreg", "svm"]))
	metric = str(rng.choice(["accuracy", "precision", "f1"]))
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=y if y.value_counts().min() >= 2 else None
	)
	if family == "tree":
		grid = list(range(3, 9))
		scores = {
			p: _metric_score(
				y_test,
				DecisionTreeClassifier(max_depth=p, random_state=seed).fit(X_train, y_train).predict(X_test),
				metric,
			)
			for p in grid
		}
		best = max(scores, key=scores.get)
		param_name = "max_depth"
	elif family == "logreg":
		# penalty options available with solvers we keep simple
		grid = ["none", "l2"]
		scores = {}
		for penalty in grid:
			kwargs = {"max_iter": 800, "random_state": seed, "solver": "lbfgs"}
			if penalty == "none":
				kwargs["penalty"] = None
			else:
				kwargs["penalty"] = penalty
			try:
				model = LogisticRegression(**kwargs).fit(X_train, y_train)
				scores[penalty] = _metric_score(y_test, model.predict(X_test), metric)
			except Exception:
				scores[penalty] = -1.0
		best = max(scores, key=scores.get)
		param_name = "penalty"
	else:
		grid = ["linear", "rbf", "poly"]
		scores = {
			k: _metric_score(
				y_test,
				SVC(kernel=k, random_state=seed).fit(X_train, y_train).predict(X_test),
				metric,
			)
			for k in grid
		}
		best = max(scores, key=scores.get)
		param_name = "kernel"
	prompt = render_prompt(
		"ml_classification",
		"medium",
		target=target,
		family=family,
		metric=metric,
		param_name=param_name,
		default=(
			f"Split `df` (target `{target}`, test_size=0.25, random_state={seed}). "
			f"Tune a {family} classifier over the prompt's parameter grid and pick the best "
			f"test {metric}. Store `answer['family']`, `answer['best_param']`, "
			f"`answer['metric']='{metric}'`, and `answer['score']` (4 decimals)."
		),
	)
	return {
		"mode": "tune_one",
		"prompt": prompt,
		"target": target,
		"expected": {
			"family": family,
			"best_param": best,
			"metric": metric,
			"score": round(float(scores[best]), 4),
			"param_name": param_name,
		},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def _build_hard(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	y = _prepare_y(y)
	scaler_name = str(rng.choice(["standard", "minmax"]))
	family = str(rng.choice(["tree", "logreg", "svm"]))
	metric = str(rng.choice(["accuracy", "precision", "f1"]))
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=y if y.value_counts().min() >= 2 else None
	)
	scaler = StandardScaler() if scaler_name == "standard" else MinMaxScaler()
	X_train_s = scaler.fit_transform(X_train)
	X_test_s = scaler.transform(X_test)
	if family == "tree":
		model = DecisionTreeClassifier(max_depth=5, random_state=seed)
	elif family == "logreg":
		model = LogisticRegression(max_iter=800, random_state=seed)
	else:
		model = SVC(kernel="rbf", random_state=seed)
	model.fit(X_train_s, y_train)
	score = _metric_score(y_test, model.predict(X_test_s), metric)
	prompt = render_prompt(
		"ml_classification",
		"hard",
		target=target,
		scaler=scaler_name,
		family=family,
		metric=metric,
		default=(
			f"Split `df` (target `{target}`, random_state={seed}), scale with {scaler_name}, "
			f"train a {family} classifier, and report test {metric} in `answer['score']` "
			f"(4 decimals). Also set `answer['family']`, `answer['scaler']`, and `answer['metric']`."
		),
	)
	return {
		"mode": "scaled_chosen",
		"prompt": prompt,
		"target": target,
		"expected": {
			"family": family,
			"scaler": scaler_name,
			"metric": metric,
			"score": round(float(score), 4),
		},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def prepare_ml_classification(
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


def ml_classification_passes(task: dict[str, Any] | None, *, answer: Any = None, plotted: Any = None) -> bool:
	del plotted
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False
	mode = task.get("mode")
	if mode == "compare_three":
		if not name_match(answer.get("best_model"), expected["best_model"]):
			return False
		scores = answer.get("scores")
		if not isinstance(scores, dict):
			return False
		for key, value in expected["scores"].items():
			if not close_metric(scores.get(key), value, tol=0.08):
				return False
		return True
	if mode == "tune_one":
		best = answer.get("best_param")
		exp_best = expected["best_param"]
		# Allow string/int for penalty/kernel/depth
		if str(best).lower() != str(exp_best).lower() and best != exp_best:
			try:
				if int(best) != int(exp_best):
					return False
			except Exception:
				return False
		return (
			name_match(answer.get("family"), expected["family"])
			and name_match(answer.get("metric"), expected["metric"])
			and close_metric(answer.get("score"), expected["score"], tol=0.08)
		)
	if mode == "scaled_chosen":
		return (
			name_match(answer.get("family"), expected["family"])
			and name_match(answer.get("scaler"), expected["scaler"])
			and name_match(answer.get("metric"), expected["metric"])
			and close_metric(answer.get("score"), expected["score"], tol=0.08)
		)
	return False
