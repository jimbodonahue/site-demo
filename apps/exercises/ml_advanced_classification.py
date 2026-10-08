"""ML Exercise 4: Advanced classification — imbalance, thresholds, multi-class."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
	accuracy_score,
	f1_score,
	precision_score,
	recall_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

from apps.exercises.content import render_prompt
from apps.exercises.ml_common import (
	CV_FOLDS,
	build_ml_dataframe,
	close_metric,
	feature_matrix,
	make_binary_target,
	name_match,
	pick_classification_target,
)


def _binary_frame(df: pd.DataFrame, target: str, seed: int) -> tuple[pd.DataFrame, pd.Series]:
	X, y = feature_matrix(df, target=target, encode=True)
	y_bin = make_binary_target(y, minority_frac=0.22, seed=seed)
	keep = y_bin != -1
	X_out = X.loc[keep].reset_index(drop=True)
	y_out = y_bin.loc[keep].astype(int).reset_index(drop=True)
	if int(y_out.nunique()) < 2 or int(y_out.value_counts().min()) < 2:
		# Fallback: majority vs rest on the encoded label, no aggressive downsample.
		top = y.value_counts().index[0]
		y_out = (y == top).astype(int).reset_index(drop=True)
		X_out = X.reset_index(drop=True)
	return X_out, y_out


def _safe_stratify(y: pd.Series):
	"""Return ``y`` for stratified splits when every class has ≥2 samples."""
	counts = y.value_counts()
	if len(counts) >= 2 and int(counts.min()) >= 2:
		return y
	return None


def _metrics(y_true, y_pred) -> dict[str, float]:
	return {
		"accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
		"precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
		"recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
		"f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
	}


def _build_easy(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = _binary_frame(df, target, seed)
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=_safe_stratify(y)
	)
	models = {
		"tree": DecisionTreeClassifier(max_depth=4, random_state=seed),
		"logreg": LogisticRegression(max_iter=400, solver="liblinear", random_state=seed),
		"svm": SVC(kernel="rbf", random_state=seed),
	}
	table = {}
	for name, model in models.items():
		model.fit(X_train, y_train)
		table[name] = _metrics(y_test, model.predict(X_test))
	# With imbalance, recall on the minority class is typically most important.
	important = "recall"
	prompt = render_prompt(
		"ml_advanced_classification",
		"easy",
		target=target,
		default=(
			f"The pre-split binary target (from `{target}`) is intentionally imbalanced. "
			"Train tree / logreg / SVM on the training set and report accuracy, precision, recall, "
			"and F1 for each in `answer['metrics']`. Set `answer['most_important_metric']` to the "
			"metric that matters most under class imbalance among those four "
			"(expect `'recall'` here)."
		),
	)
	return {
		"mode": "imbalance_report",
		"prompt": prompt,
		"target": target,
		"expected": {"metrics": table, "most_important_metric": important},
		"X_train": X_train,
		"X_test": X_test,
		"y_train": y_train,
		"y_test": y_test,
	}


def _build_medium(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng)
	X, y = _binary_frame(df, target, seed)
	X_train, X_test, y_train, y_test = train_test_split(
		X, y, test_size=0.25, random_state=seed, stratify=_safe_stratify(y)
	)
	goal = str(rng.choice(["recall", "precision"]))
	target_value = 0.70
	base = LogisticRegression(max_iter=400, solver="liblinear", random_state=seed).fit(X_train, y_train)
	weighted = LogisticRegression(
		max_iter=400, solver="liblinear", class_weight="balanced", random_state=seed
	).fit(X_train, y_train)
	base_m = _metrics(y_test, base.predict(X_test))
	weighted_m = _metrics(y_test, weighted.predict(X_test))
	# Threshold search on weighted model probabilities
	proba = weighted.predict_proba(X_test)[:, 1]
	best_thresh = 0.5
	best_score = -1.0
	for thresh in np.linspace(0.2, 0.8, 13):
		preds = (proba >= thresh).astype(int)
		score = recall_score(y_test, preds, zero_division=0) if goal == "recall" else precision_score(
			y_test, preds, zero_division=0
		)
		if score >= target_value and score > best_score:
			best_score = float(score)
			best_thresh = float(thresh)
	if best_score < 0:
		# Fall back to the threshold with the best goal score.
		for thresh in np.linspace(0.2, 0.8, 13):
			preds = (proba >= thresh).astype(int)
			score = recall_score(y_test, preds, zero_division=0) if goal == "recall" else precision_score(
				y_test, preds, zero_division=0
			)
			if score > best_score:
				best_score = float(score)
				best_thresh = float(thresh)
	prompt = render_prompt(
		"ml_advanced_classification",
		"medium",
		target=target,
		goal=goal,
		default=(
			f"On the imbalanced binary problem from `{target}`, compare a default logistic regression "
			"to a class-weighted one. Then choose a decision threshold ≠ 0.5 on the weighted model "
			f"to prioritize {goal}. Store `answer['default_f1']`, `answer['weighted_f1']`, "
			f"`answer['threshold']` (2 decimals), and `answer['goal_score']` for {goal} at that threshold."
		),
	)
	return {
		"mode": "threshold_tune",
		"prompt": prompt,
		"target": target,
		"expected": {
			"default_f1": base_m["f1"],
			"weighted_f1": weighted_m["f1"],
			"threshold": round(best_thresh, 2),
			"goal": goal,
			"goal_score": round(best_score, 4),
		},
		"X_train": X_train,
		"X_test": X_test,
		"y_train": y_train,
		"y_test": y_test,
	}


def _build_hard(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	target = pick_classification_target(df, rng, max_classes=4)
	X, y_raw = feature_matrix(df, target=target, encode=True)
	if y_raw.nunique() < 3:
		# Manufacture 3 classes from tertiles when needed.
		y = pd.qcut(pd.to_numeric(y_raw, errors="coerce").rank(method="first"), 3, labels=False)
	else:
		y = pd.Series(pd.Categorical(y_raw).codes, index=y_raw.index).astype(int)
	# Keep at most 4 classes
	keep_classes = sorted(y.value_counts().index.tolist())[:4]
	mask = y.isin(keep_classes)
	X, y = X.loc[mask].reset_index(drop=True), y.loc[mask].reset_index(drop=True)
	# Remap codes
	mapping = {old: i for i, old in enumerate(sorted(y.unique()))}
	y = y.map(mapping).astype(int)
	cv = StratifiedKFold(n_splits=CV_FOLDS, shuffle=True, random_state=seed)
	tree = DecisionTreeClassifier(max_depth=5, random_state=seed)
	logreg = LogisticRegression(max_iter=800, random_state=seed)
	tree_pred = cross_val_predict(tree, X, y, cv=cv)
	log_pred = cross_val_predict(logreg, X, y, cv=cv)
	tree_macro = float(f1_score(y, tree_pred, average="macro", zero_division=0))
	log_macro = float(f1_score(y, log_pred, average="macro", zero_division=0))
	tree_micro = float(f1_score(y, tree_pred, average="micro", zero_division=0))
	log_micro = float(f1_score(y, log_pred, average="micro", zero_division=0))
	winner = "tree" if tree_macro >= log_macro else "logreg"
	# Calibration reference on logistic regression
	calibrated = CalibratedClassifierCV(LogisticRegression(max_iter=800, random_state=seed), cv=CV_FOLDS)
	calibrated.fit(X, y)
	prompt = render_prompt(
		"ml_advanced_classification",
		"hard",
		target=target,
		k=CV_FOLDS,
		default=(
			f"Treat `{target}` as a multi-class label. Compare a decision tree and logistic regression "
			f"with {CV_FOLDS}-fold stratified CV. Report macro and micro F1 for both in "
			"`answer['macro_f1']` / `answer['micro_f1']` dicts keyed by `'tree'` and `'logreg'`, "
			"and set `answer['best_model']` to the higher macro-F1 model. "
			"Also set `answer['calibrated']=True` after fitting a calibrated logistic model."
		),
	)
	return {
		"mode": "multiclass_cv",
		"prompt": prompt,
		"target": target,
		"expected": {
			"macro_f1": {"tree": round(tree_macro, 4), "logreg": round(log_macro, 4)},
			"micro_f1": {"tree": round(tree_micro, 4), "logreg": round(log_micro, 4)},
			"best_model": winner,
			"calibrated": True,
		},
		"X_train": None,
		"X_test": None,
		"y_train": None,
		"y_test": None,
	}


def prepare_ml_advanced_classification(
	difficulty: str = "easy",
	seed: int = 42,
	rows: int = 110,
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


def ml_advanced_classification_passes(
	task: dict[str, Any] | None, *, answer: Any = None, plotted: Any = None
) -> bool:
	del plotted
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False
	mode = task.get("mode")
	if mode == "imbalance_report":
		if not name_match(answer.get("most_important_metric"), expected["most_important_metric"]):
			return False
		metrics = answer.get("metrics")
		if not isinstance(metrics, dict):
			return False
		for model, want in expected["metrics"].items():
			got = metrics.get(model)
			if not isinstance(got, dict):
				return False
			for key, value in want.items():
				if not close_metric(got.get(key), value, tol=0.1):
					return False
		return True
	if mode == "threshold_tune":
		return (
			close_metric(answer.get("default_f1"), expected["default_f1"], tol=0.1)
			and close_metric(answer.get("weighted_f1"), expected["weighted_f1"], tol=0.1)
			and close_metric(answer.get("threshold"), expected["threshold"], tol=0.15)
			and close_metric(answer.get("goal_score"), expected["goal_score"], tol=0.12)
		)
	if mode == "multiclass_cv":
		if not name_match(answer.get("best_model"), expected["best_model"]):
			return False
		if answer.get("calibrated") not in {True, 1, "true", "True"}:
			return False
		for bucket in ("macro_f1", "micro_f1"):
			got = answer.get(bucket)
			want = expected[bucket]
			if not isinstance(got, dict):
				return False
			for key, value in want.items():
				if not close_metric(got.get(key), value, tol=0.12):
					return False
		return True
	return False
