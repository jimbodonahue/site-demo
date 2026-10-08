"""Shared helpers for Machine Learning track exercises."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from apps.exercises.data_zoo import sample_zoo_dataframe

DEFAULT_ROWS = 100
DEFAULT_SECTOR = "marketing"
CV_FOLDS = 3
RF_TREES = 25
XGB_TREES = 25


def _sector(**kwargs: Any) -> str:
	sector = kwargs.get("data_field") or kwargs.get("topic") or kwargs.get("sector") or DEFAULT_SECTOR
	return str(sector).strip().lower() or DEFAULT_SECTOR


def classify_ml_columns(df: pd.DataFrame) -> dict[str, list[str]]:
	"""Split columns into numeric features, categorical features, and a target candidate."""
	numeric: list[str] = []
	categorical: list[str] = []
	for column in df.columns:
		series = df[column]
		if pd.api.types.is_bool_dtype(series):
			categorical.append(str(column))
			continue
		if pd.api.types.is_numeric_dtype(series):
			nunique = int(series.nunique(dropna=True))
			if 1 < nunique <= 8 and not pd.api.types.is_float_dtype(series):
				categorical.append(str(column))
			else:
				numeric.append(str(column))
			continue
		nunique = int(series.nunique(dropna=True))
		if 1 < nunique <= 16:
			categorical.append(str(column))
	return {"numeric": numeric, "categorical": categorical}


def pick_regression_target(df: pd.DataFrame, rng: np.random.Generator) -> str:
	roles = classify_ml_columns(df)
	numeric = [c for c in roles["numeric"] if df[c].nunique(dropna=True) > 8]
	if not numeric:
		numeric = roles["numeric"]
	if not numeric:
		raise ValueError("No numeric target available for regression.")
	return str(rng.choice(numeric))


def pick_classification_target(df: pd.DataFrame, rng: np.random.Generator, *, max_classes: int = 4) -> str:
	roles = classify_ml_columns(df)
	candidates = []
	for column in roles["categorical"] + roles["numeric"]:
		nunique = int(df[column].nunique(dropna=True))
		if 2 <= nunique <= max_classes:
			candidates.append(column)
	if not candidates:
		# Fall back to median-split of a numeric column.
		numeric = roles["numeric"]
		if not numeric:
			raise ValueError("No classification target available.")
		return str(rng.choice(numeric))
	return str(rng.choice(candidates))


def build_ml_dataframe(
	*,
	rows: int = DEFAULT_ROWS,
	seed: int = 42,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> pd.DataFrame:
	"""Load a zoo sample and drop sparse / non-feature columns."""
	sector = _sector(data_field=data_field, topic=topic)
	frame = sample_zoo_dataframe(
		sector,
		rows=max(40, int(rows)),
		seed=seed,
		dataset_file=(dataset_file or None),
	).copy()
	# Drop columns that are mostly missing or unique IDs.
	keep = []
	for column in frame.columns:
		series = frame[column]
		if series.isna().mean() > 0.4:
			continue
		nunique = int(series.nunique(dropna=True))
		if nunique <= 1:
			continue
		if nunique >= len(frame) * 0.95 and not pd.api.types.is_float_dtype(series):
			continue
		keep.append(column)
	if len(keep) < 3:
		keep = list(frame.columns)[: min(8, len(frame.columns))]
	out = frame.loc[:, keep].copy()
	out = out.dropna(axis=0, how="any").reset_index(drop=True)
	if len(out) < 30:
		# Fill remaining NA lightly so tiny zoo samples still work.
		out = frame.loc[:, keep].copy()
		for column in out.columns:
			if pd.api.types.is_numeric_dtype(out[column]):
				out[column] = out[column].fillna(out[column].median())
			else:
				mode = out[column].mode(dropna=True)
				fill = mode.iloc[0] if len(mode) else "unknown"
				out[column] = out[column].fillna(fill)
		out = out.reset_index(drop=True)
	return out


def feature_matrix(
	df: pd.DataFrame,
	*,
	target: str,
	encode: bool = False,
) -> tuple[pd.DataFrame, pd.Series]:
	"""Build X/y, optionally one-hot encoding categoricals."""
	y = df[target].copy()
	X = df.drop(columns=[target]).copy()
	if encode:
		cat_cols = [
			c
			for c in X.columns
			if (not pd.api.types.is_numeric_dtype(X[c]))
			or (pd.api.types.is_integer_dtype(X[c]) and X[c].nunique() <= 8)
		]
		num_cols = [c for c in X.columns if c not in cat_cols]
		parts = []
		if num_cols:
			parts.append(X[num_cols].apply(pd.to_numeric, errors="coerce"))
		if cat_cols:
			dummies = pd.get_dummies(X[cat_cols].astype(str), drop_first=False)
			parts.append(dummies.astype(float))
		X = pd.concat(parts, axis=1) if parts else X
		X = X.fillna(0.0)
	else:
		# Keep numeric only when not encoding.
		X = X.select_dtypes(include=[np.number]).copy()
		X = X.fillna(X.median(numeric_only=True))
	# Ensure y is usable.
	if not pd.api.types.is_numeric_dtype(y):
		y = y.astype("category").cat.codes.astype(int)
	else:
		y = pd.to_numeric(y, errors="coerce")
		if y.isna().any():
			y = y.fillna(y.median())
	return X.reset_index(drop=True), y.reset_index(drop=True)


def make_binary_target(y: pd.Series, *, minority_frac: float = 0.2, seed: int = 42) -> pd.Series:
	"""Turn a label into an imbalanced binary target when needed.

	Dropped majority rows are marked ``-1`` so callers can filter them out.
	Always returns at least two real classes when the input has any variation.
	"""
	rng = np.random.default_rng(seed)
	raw = y.copy()
	nunique = int(raw.nunique(dropna=True))

	if nunique <= 1:
		# Manufacture a binary label from row order when the column is constant.
		ranks = pd.Series(np.arange(len(raw)), index=raw.index)
		values = (ranks >= len(raw) // 2).astype(int)
	elif nunique == 2:
		codes = pd.Categorical(raw).codes
		values = pd.Series(codes, index=y.index).astype(int)
	elif pd.api.types.is_numeric_dtype(raw) and nunique > 8:
		# Continuous: quantile split that keeps both sides non-empty.
		threshold = float(raw.quantile(0.65))
		values = (raw >= threshold).astype(int)
		if int(values.nunique()) < 2:
			threshold = float(raw.quantile(0.35))
			values = (raw >= threshold).astype(int)
	else:
		# Low-cardinality / categorical: majority class vs the rest.
		top = raw.value_counts().index[0]
		values = (raw == top).astype(int)

	if int(values.nunique()) < 2:
		ranks = pd.to_numeric(raw, errors="coerce")
		if ranks.isna().all():
			ranks = pd.Series(np.arange(len(raw)), index=raw.index, dtype=float)
		else:
			ranks = ranks.fillna(ranks.median()).rank(method="first")
		values = (ranks > ranks.median()).astype(int)

	# Enforce imbalance by downsampling the majority class (caller filters -1 rows).
	counts = values.value_counts()
	if len(counts) < 2:
		return values
	minority = int(counts.idxmin())
	majority = int(counts.idxmax())
	minority_idx = values[values == minority].index.to_numpy()
	majority_idx = values[values == majority].index.to_numpy()
	# Keep enough majority rows for ~minority_frac of the retained sample, but never
	# drop below 2 of either class (needed for stratified splits).
	target_majority = max(
		2,
		int(round(len(minority_idx) * (1.0 - minority_frac) / max(minority_frac, 1e-6))),
	)
	target_majority = min(target_majority, len(majority_idx))
	if len(majority_idx) > target_majority and len(minority_idx) >= 2:
		keep_maj = rng.choice(majority_idx, size=target_majority, replace=False)
		keep = np.concatenate([minority_idx, keep_maj])
		mask = values.index.isin(keep)
		out = values.copy()
		out.loc[~mask] = -1
		return out
	return values


def close_metric(actual: Any, expected: float, tol: float = 0.05) -> bool:
	try:
		return abs(float(actual) - float(expected)) <= tol
	except (TypeError, ValueError):
		return False


def name_match(actual: Any, expected: str) -> bool:
	if actual is None:
		return False
	return str(actual).strip().lower() == str(expected).strip().lower()


def boolish(value: Any) -> bool | None:
	if isinstance(value, (bool, np.bool_)):
		return bool(value)
	if isinstance(value, (int, np.integer)) and value in (0, 1):
		return bool(value)
	if isinstance(value, str):
		lower = value.strip().lower()
		if lower in {"true", "yes", "y", "1", "good"}:
			return True
		if lower in {"false", "no", "n", "0", "bad"}:
			return False
	return None
