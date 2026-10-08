"""ML Exercise 5: Ensemble methods — random forest and XGBoost (kept small)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from apps.exercises.content import render_prompt
from apps.exercises.ml_common import (
	RF_TREES,
	XGB_TREES,
	build_ml_dataframe,
	close_metric,
	feature_matrix,
	name_match,
	pick_classification_target,
)

try:
	from xgboost import XGBClassifier
except Exception:  # pragma: no cover
	XGBClassifier = None  # type: ignore


def _metric_score(y_true, y_pred, metric: str) -> float:
	average = "binary" if len(np.unique(y_true)) <= 2 else "macro"
	if metric == "precision":
		return float(precision_score(y_true, y_pred, average=average, zero_division=0))
	if metric == "f1":
		return float(f1_score(y_true, y_pred, average=average, zero_division=0))
	return float(accuracy_score(y_true, y_pred))


def _prep_y(y: pd.Series) -> pd.Series:
	if y.nunique() > 6:
		return (y >= y.median()).astype(int)
	if not pd.api.types.is_integer_dtype(y):
		return pd.Series(pd.Categorical(y).codes, index=y.index).astype(int)
	return y.astype(int)


def _xgb(**kwargs):
	if XGBClassifier is None:
		raise RuntimeError("xgboost is not installed")
	params = {
		"n_estimators": XGB_TREES,
		"max_depth": 3,
		"learning_rate": 0.2,
		"subsample": 0.9,
		"colsample_bytree": 0.9,
		"eval_metric": "logloss",
		"verbosity": 0,
	}
	params.update(kwargs)
	return XGBClassifier(**params)


def _build_easy(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	y = _prep_y(y)
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=y if y.value_counts().min() >= 2 else None
	)
	rf = RandomForestClassifier(n_estimators=RF_TREES, max_depth=4, random_state=seed, n_jobs=1)
	xgb = _xgb(random_state=seed)
	rf.fit(X_train, y_train)
	xgb.fit(X_train, y_train)
	rf_acc = _metric_score(y_test, rf.predict(X_test), "accuracy")
	xgb_acc = _metric_score(y_test, xgb.predict(X_test), "accuracy")
	winner = "random_forest" if rf_acc >= xgb_acc else "xgboost"
	prompt = render_prompt(
		"ml_ensembles",
		"easy",
		target=target,
		rf_trees=RF_TREES,
		xgb_trees=XGB_TREES,
		default=(
			f"Using the pre-split arrays for `{target}`, train a RandomForestClassifier "
			f"(n_estimators={RF_TREES}, max_depth=4) and an XGBClassifier "
			f"(n_estimators={XGB_TREES}, max_depth=3). Compare test accuracy and set "
			"`answer['best_model']` to `'random_forest'` or `'xgboost'`. "
			"Also store `answer['rf_accuracy']` and `answer['xgb_accuracy']` (4 decimals)."
		),
	)
	return {
		"mode": "compare_two",
		"prompt": prompt,
		"target": target,
		"expected": {
			"best_model": winner,
			"rf_accuracy": round(rf_acc, 4),
			"xgb_accuracy": round(xgb_acc, 4),
		},
		"X_train": X_train,
		"X_test": X_test,
		"y_train": y_train,
		"y_test": y_test,
	}


def _build_medium(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	y = _prep_y(y)
	family = str(rng.choice(["random_forest", "xgboost"]))
	metric = str(rng.choice(["accuracy", "precision", "f1"]))
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=y if y.value_counts().min() >= 2 else None
	)
	if family == "random_forest":
		grid = {
			"max_depth": [3, 4, 5],
			"min_samples_leaf": [1, 3, 5],
		}
		# Tune two hyperparameters independently then pick best combo of a small grid.
		best = {"max_depth": 3, "min_samples_leaf": 1}
		best_score = -1.0
		for depth in grid["max_depth"]:
			for leaf in grid["min_samples_leaf"]:
				model = RandomForestClassifier(
					n_estimators=RF_TREES,
					max_depth=depth,
					min_samples_leaf=leaf,
					random_state=seed,
					n_jobs=1,
				).fit(X_train, y_train)
				score = _metric_score(y_test, model.predict(X_test), metric)
				if score > best_score:
					best_score = score
					best = {"max_depth": depth, "min_samples_leaf": leaf}
		param_keys = ["max_depth", "min_samples_leaf"]
	else:
		grid = {"max_depth": [2, 3, 4], "learning_rate": [0.1, 0.2, 0.3]}
		best = {"max_depth": 2, "learning_rate": 0.1}
		best_score = -1.0
		for depth in grid["max_depth"]:
			for lr in grid["learning_rate"]:
				model = _xgb(max_depth=depth, learning_rate=lr, random_state=seed).fit(X_train, y_train)
				score = _metric_score(y_test, model.predict(X_test), metric)
				if score > best_score:
					best_score = score
					best = {"max_depth": depth, "learning_rate": lr}
		param_keys = ["max_depth", "learning_rate"]
	prompt = render_prompt(
		"ml_ensembles",
		"medium",
		target=target,
		family=family,
		metric=metric,
		param_keys=param_keys,
		default=(
			f"Split `df` (target `{target}`, random_state={seed}). Tune `{family}` on hyperparameters "
			f"{param_keys} using a small grid of 3 values each. Report the best test {metric} in "
			"`answer['score']`, `answer['family']`, and `answer['best_params']` as a dict."
		),
	)
	return {
		"mode": "tune_two",
		"prompt": prompt,
		"target": target,
		"expected": {
			"family": family,
			"metric": metric,
			"score": round(float(best_score), 4),
			"best_params": best,
		},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def _build_hard(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	y = _prep_y(y)
	scaler_name = str(rng.choice(["standard", "minmax"]))
	family = str(rng.choice(["random_forest", "xgboost"]))
	metric = str(rng.choice(["accuracy", "precision", "f1"]))
	# Optionally drop a couple of low-variance columns
	variances = X.var(numeric_only=True).sort_values()
	drop_cols = list(variances.head(min(2, max(0, len(variances) - 3))).index)
	X_use = X.drop(columns=drop_cols) if drop_cols else X
	X_train, X_test, y_train, y_test = train_test_split(
		X_use, y, test_size=0.25, random_state=seed, stratify=y if y.value_counts().min() >= 2 else None
	)
	scaler = StandardScaler() if scaler_name == "standard" else MinMaxScaler()
	X_train_s = scaler.fit_transform(X_train)
	X_test_s = scaler.transform(X_test)
	if family == "random_forest":
		model = RandomForestClassifier(
			n_estimators=RF_TREES, max_depth=4, min_samples_leaf=2, random_state=seed, n_jobs=1
		)
		best_params = {"max_depth": 4, "min_samples_leaf": 2, "n_estimators": RF_TREES}
	else:
		model = _xgb(max_depth=3, learning_rate=0.2, random_state=seed)
		best_params = {"max_depth": 3, "learning_rate": 0.2, "n_estimators": XGB_TREES}
	model.fit(X_train_s, y_train)
	score = _metric_score(y_test, model.predict(X_test_s), metric)
	prompt = render_prompt(
		"ml_ensembles",
		"hard",
		target=target,
		scaler=scaler_name,
		family=family,
		metric=metric,
		dropped=drop_cols,
		default=(
			f"Split `df` (target `{target}`, random_state={seed}), scale with {scaler_name}, "
			f"optionally drop low-variance columns {drop_cols}, then tune/fit `{family}`. "
			f"Report test {metric} in `answer['score']`, plus `answer['family']`, "
			"`answer['scaler']`, `answer['dropped_columns']`, and `answer['best_params']`."
		),
	)
	return {
		"mode": "scaled_search",
		"prompt": prompt,
		"target": target,
		"expected": {
			"family": family,
			"scaler": scaler_name,
			"metric": metric,
			"score": round(float(score), 4),
			"dropped_columns": drop_cols,
			"best_params": best_params,
		},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def prepare_ml_ensembles(
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


def ml_ensembles_passes(task: dict[str, Any] | None, *, answer: Any = None, plotted: Any = None) -> bool:
	del plotted
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False
	mode = task.get("mode")
	if mode == "compare_two":
		return (
			name_match(answer.get("best_model"), expected["best_model"])
			and close_metric(answer.get("rf_accuracy"), expected["rf_accuracy"], tol=0.1)
			and close_metric(answer.get("xgb_accuracy"), expected["xgb_accuracy"], tol=0.1)
		)
	if mode == "tune_two":
		params = answer.get("best_params")
		want = expected["best_params"]
		if not isinstance(params, dict):
			return False
		for key, value in want.items():
			got = params.get(key)
			try:
				if abs(float(got) - float(value)) > 1e-6 and got != value:
					return False
			except Exception:
				if got != value:
					return False
		return (
			name_match(answer.get("family"), expected["family"])
			and name_match(answer.get("metric"), expected["metric"])
			and close_metric(answer.get("score"), expected["score"], tol=0.1)
		)
	if mode == "scaled_search":
		dropped = answer.get("dropped_columns") or []
		want_dropped = set(map(str, expected.get("dropped_columns") or []))
		if set(map(str, dropped)) != want_dropped:
			return False
		return (
			name_match(answer.get("family"), expected["family"])
			and name_match(answer.get("scaler"), expected["scaler"])
			and name_match(answer.get("metric"), expected["metric"])
			and close_metric(answer.get("score"), expected["score"], tol=0.12)
		)
	return False
