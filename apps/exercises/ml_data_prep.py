"""ML Exercise 1: Data preparation — split quality, encoding, scaling, K-fold."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, train_test_split
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from apps.exercises.content import render_prompt
from apps.exercises.ml_common import (
	CV_FOLDS,
	boolish,
	build_ml_dataframe,
	close_metric,
	feature_matrix,
	name_match,
	pick_regression_target,
)


def _split_quality_report(
	X_train: pd.DataFrame,
	X_test: pd.DataFrame,
	y_train: pd.Series,
	y_test: pd.Series,
) -> dict[str, Any]:
	"""Heuristic: a split is 'good' when feature/target means are close."""
	train_means = X_train.mean(numeric_only=True)
	test_means = X_test.mean(numeric_only=True)
	shared = [c for c in train_means.index if c in test_means.index]
	if not shared:
		feature_gap = 0.0
	else:
		diffs = []
		for col in shared:
			scale = max(abs(float(train_means[col])), 1e-6)
			diffs.append(abs(float(train_means[col]) - float(test_means[col])) / scale)
		feature_gap = float(np.mean(diffs)) if diffs else 0.0
	y_scale = max(abs(float(y_train.mean())), 1e-6)
	target_gap = abs(float(y_train.mean()) - float(y_test.mean())) / y_scale
	# Relatively loose — zoo samples are small.
	good = feature_gap < 0.35 and target_gap < 0.35
	return {
		"good": good,
		"feature_mean_gap": round(feature_gap, 4),
		"target_mean_gap": round(target_gap, 4),
		"train_target_mean": round(float(y_train.mean()), 4),
		"test_target_mean": round(float(y_test.mean()), 4),
	}


def _build_easy(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_regression_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=int(seed)
	)
	report = _split_quality_report(X_train, X_test, y_train, y_test)
	prompt = render_prompt(
		"ml_data_prep",
		"easy",
		target=target,
		default=(
			f"The platform already split `{target}` into train/test arrays "
			"(`X_train`, `X_test`, `y_train`, `y_test`). "
			"Compare descriptive statistics (or a tiny linear fit) between train and test, "
			"then set `answer['split_quality']` to `'good'` or `'bad'`. "
			"Also store `answer['train_target_mean']` and `answer['test_target_mean']` "
			"(rounded to 4 decimals)."
		),
	)
	return {
		"difficulty": "easy",
		"mode": "split_check",
		"prompt": prompt,
		"target": target,
		"expected": {
			"split_quality": "good" if report["good"] else "bad",
			"train_target_mean": report["train_target_mean"],
			"test_target_mean": report["test_target_mean"],
		},
		"X_train": X_train,
		"X_test": X_test,
		"y_train": y_train,
		"y_test": y_test,
	}


def _build_medium(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_regression_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	n_splits = int(rng.integers(3, 5))  # 3–4
	seeds = [int(seed) + 17 * i for i in range(n_splits)]
	means = []
	for split_seed in seeds:
		_X_train, _X_test, y_train, y_test = train_test_split(
			X, y, test_size=0.25, random_state=split_seed
		)
		means.append(
			{
				"seed": split_seed,
				"train_target_mean": round(float(y_train.mean()), 4),
				"test_target_mean": round(float(y_test.mean()), 4),
			}
		)
	prompt = render_prompt(
		"ml_data_prep",
		"medium",
		target=target,
		n_splits=n_splits,
		seeds=seeds,
		default=(
			f"One-hot encode categoricals with `{target}` as the target, then split into train/test "
			f"{n_splits} times using seeds {seeds}. "
			"Store `answer['means']` as a list of dicts with keys "
			"`seed`, `train_target_mean`, `test_target_mean` (means rounded to 4 decimals), "
			"in the same seed order."
		),
	)
	return {
		"difficulty": "medium",
		"mode": "multi_split",
		"prompt": prompt,
		"target": target,
		"seeds": seeds,
		"n_splits": n_splits,
		"expected": {"means": means},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def _build_hard(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_regression_target(df, rng)
	X, y = feature_matrix(df, target=target, encode=True)
	scaler_name = str(rng.choice(["standard", "minmax"]))
	k = CV_FOLDS
	if scaler_name == "standard":
		scaler = StandardScaler()
	else:
		scaler = MinMaxScaler()
	X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=X.columns)
	kf = KFold(n_splits=k, shuffle=True, random_state=int(seed))
	fold_means = []
	for fold_idx, (train_idx, test_idx) in enumerate(kf.split(X_scaled)):
		y_train = y.iloc[train_idx]
		y_test = y.iloc[test_idx]
		fold_means.append(
			{
				"fold": fold_idx,
				"train_target_mean": round(float(y_train.mean()), 4),
				"test_target_mean": round(float(y_test.mean()), 4),
			}
		)
	prompt = render_prompt(
		"ml_data_prep",
		"hard",
		target=target,
		scaler=scaler_name,
		k=k,
		default=(
			f"One-hot encode features for target `{target}`, scale with a "
			f"{scaler_name} scaler, then run {k}-fold CV (shuffle=True, random_state={seed}). "
			"Store `answer['fold_means']` as a list of dicts with keys "
			"`fold`, `train_target_mean`, `test_target_mean` (rounded to 4 decimals), "
			"in fold order 0..K-1. Also set `answer['scaler']` to "
			f"'{scaler_name}'."
		),
	)
	return {
		"difficulty": "hard",
		"mode": "kfold_scaled",
		"prompt": prompt,
		"target": target,
		"scaler": scaler_name,
		"k": k,
		"expected": {"fold_means": fold_means, "scaler": scaler_name},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def prepare_ml_data_prep(
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
		rows=rows,
		seed=seed,
		data_field=data_field,
		dataset_file=dataset_file,
		topic=topic,
	)
	builders = {"easy": _build_easy, "medium": _build_medium, "hard": _build_hard}
	payload = builders[difficulty_key](df, rng, seed)
	task = {
		"difficulty": payload["difficulty"],
		"mode": payload["mode"],
		"prompt": payload["prompt"],
		"target": payload["target"],
		"expected": payload["expected"],
		"seeds": payload.get("seeds"),
		"scaler": payload.get("scaler"),
		"k": payload.get("k"),
		"n_splits": payload.get("n_splits"),
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


def ml_data_prep_passes(task: dict[str, Any] | None, *, answer: Any = None, plotted: Any = None) -> bool:
	del plotted  # plotting bonus is graded separately
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False
	mode = task.get("mode")
	if mode == "split_quality" or mode == "split_check":
		quality = str(answer.get("split_quality") or "").strip().lower()
		if quality not in {"good", "bad"}:
			return False
		if quality != str(expected.get("split_quality")).lower():
			return False
		return close_metric(answer.get("train_target_mean"), expected["train_target_mean"], tol=0.02) and close_metric(
			answer.get("test_target_mean"), expected["test_target_mean"], tol=0.02
		)
	if mode == "multi_split":
		means = answer.get("means")
		exp = expected.get("means") or []
		if not isinstance(means, list) or len(means) != len(exp):
			return False
		for got, want in zip(means, exp):
			if not isinstance(got, dict):
				return False
			if int(got.get("seed", -1)) != int(want["seed"]):
				return False
			if not close_metric(got.get("train_target_mean"), want["train_target_mean"], tol=0.02):
				return False
			if not close_metric(got.get("test_target_mean"), want["test_target_mean"], tol=0.02):
				return False
		return True
	if mode == "kfold_scaled":
		if not name_match(answer.get("scaler"), expected.get("scaler")):
			return False
		folds = answer.get("fold_means")
		exp = expected.get("fold_means") or []
		if not isinstance(folds, list) or len(folds) != len(exp):
			return False
		for got, want in zip(folds, exp):
			if not isinstance(got, dict):
				return False
			if int(got.get("fold", -1)) != int(want["fold"]):
				return False
			if not close_metric(got.get("train_target_mean"), want["train_target_mean"], tol=0.02):
				return False
			if not close_metric(got.get("test_target_mean"), want["test_target_mean"], tol=0.02):
				return False
		return True
	return False
