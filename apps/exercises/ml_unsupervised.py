"""ML Exercise 6: Unsupervised learning — K-means, K selection, PCA."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

from apps.exercises.content import render_prompt
from apps.exercises.ml_common import build_ml_dataframe, close_metric, name_match


def _numeric_matrix(df: pd.DataFrame) -> pd.DataFrame:
	X = df.select_dtypes(include=[np.number]).copy()
	X = X.dropna(axis=1, how="all")
	X = X.fillna(X.median(numeric_only=True))
	# Drop near-constant columns.
	keep = [c for c in X.columns if X[c].nunique(dropna=True) > 1]
	return X.loc[:, keep] if keep else X


def _cluster_summary(X: pd.DataFrame, labels: np.ndarray, key_cols: list[str]) -> list[dict[str, Any]]:
	frame = X.copy()
	frame["cluster"] = labels
	rows = []
	for cluster_id, group in frame.groupby("cluster"):
		entry: dict[str, Any] = {"cluster": int(cluster_id), "size": int(len(group))}
		for col in key_cols:
			if col in group.columns:
				entry[f"mean_{col}"] = round(float(group[col].mean()), 4)
		rows.append(entry)
	return sorted(rows, key=lambda r: r["cluster"])


def _build_easy(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	X = _numeric_matrix(df)
	k = int(rng.integers(2, 5))
	scaler = StandardScaler()
	Xs = scaler.fit_transform(X)
	model = KMeans(n_clusters=k, n_init=10, random_state=seed)
	labels = model.fit_predict(Xs)
	key_cols = list(X.columns[: min(3, len(X.columns))])
	summary = _cluster_summary(X, labels, key_cols)
	prompt = render_prompt(
		"ml_unsupervised",
		"easy",
		k=k,
		key_cols=key_cols,
		default=(
			f"Standardize the numeric columns of `df`, run K-means with K={k} "
			f"(random_state={seed}, n_init=10), and summarize each cluster. "
			f"Store `answer['k']={k}` and `answer['clusters']` as a list of dicts with "
			f"`cluster`, `size`, and mean_ columns for {key_cols} (means to 4 decimals)."
		),
	)
	return {
		"mode": "fixed_k",
		"prompt": prompt,
		"expected": {"k": k, "clusters": summary, "key_cols": key_cols},
	}


def _build_medium(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	del rng
	X = _numeric_matrix(df)
	scaler = StandardScaler()
	Xs = scaler.fit_transform(X)
	candidate_ks = list(range(2, 7))
	silhouettes = {}
	for k in candidate_ks:
		labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(Xs)
		silhouettes[k] = float(silhouette_score(Xs, labels))
	best_k = max(silhouettes, key=silhouettes.get)
	labels = KMeans(n_clusters=best_k, n_init=10, random_state=seed).fit_predict(Xs)
	key_cols = list(X.columns[: min(3, len(X.columns))])
	summary = _cluster_summary(X, labels, key_cols)
	prompt = render_prompt(
		"ml_unsupervised",
		"medium",
		default=(
			f"Standardize numeric features, evaluate K-means for K in {candidate_ks} using silhouette "
			f"score (random_state={seed}), choose the best K, then summarize clusters. "
			"Store `answer['best_k']`, `answer['silhouette']` (4 decimals), and `answer['clusters']`."
		),
	)
	return {
		"mode": "choose_k",
		"prompt": prompt,
		"expected": {
			"best_k": int(best_k),
			"silhouette": round(silhouettes[best_k], 4),
			"clusters": summary,
			"key_cols": key_cols,
		},
	}


def _build_hard(df: pd.DataFrame, rng: np.random.Generator, seed: int) -> dict[str, Any]:
	del rng
	X = _numeric_matrix(df)
	scaler = StandardScaler()
	Xs = scaler.fit_transform(X)
	n_components = 2 if Xs.shape[1] >= 2 else 1
	pca = PCA(n_components=n_components, random_state=seed)
	Xp = pca.fit_transform(Xs)
	candidate_ks = list(range(2, 6))
	sil_full = {}
	sil_pca = {}
	for k in candidate_ks:
		labels_full = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(Xs)
		labels_pca = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(Xp)
		sil_full[k] = float(silhouette_score(Xs, labels_full))
		sil_pca[k] = float(silhouette_score(Xp, labels_pca))
	best_full = max(sil_full, key=sil_full.get)
	best_pca = max(sil_pca, key=sil_pca.get)
	better = "pca" if sil_pca[best_pca] >= sil_full[best_full] else "full"
	prompt = render_prompt(
		"ml_unsupervised",
		"hard",
		n_components=n_components,
		default=(
			f"Standardize numeric features, run PCA to {n_components} components, and compare "
			f"K-means (K in {candidate_ks}) on the full scaled space vs the PCA space using silhouette. "
			"Store `answer['best_k_full']`, `answer['best_k_pca']`, "
			"`answer['silhouette_full']`, `answer['silhouette_pca']` (4 decimals), "
			"and `answer['better_space']` as `'full'` or `'pca'`."
		),
	)
	return {
		"mode": "pca_compare",
		"prompt": prompt,
		"expected": {
			"best_k_full": int(best_full),
			"best_k_pca": int(best_pca),
			"silhouette_full": round(sil_full[best_full], 4),
			"silhouette_pca": round(sil_pca[best_pca], 4),
			"better_space": better,
			"n_components": n_components,
		},
	}


def prepare_ml_unsupervised(
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
		"seed": seed,
		"expected": payload["expected"],
	}
	return {"df": df, "task": task, "answer": None, "plotted": None}


def ml_unsupervised_passes(task: dict[str, Any] | None, *, answer: Any = None, plotted: Any = None) -> bool:
	del plotted
	task = task or {}
	expected = task.get("expected") or {}
	if not isinstance(answer, dict):
		return False
	mode = task.get("mode")
	if mode == "fixed_k":
		if int(answer.get("k", -1)) != int(expected["k"]):
			return False
		clusters = answer.get("clusters")
		want = expected["clusters"]
		if not isinstance(clusters, list) or len(clusters) != len(want):
			return False
		for got, exp in zip(sorted(clusters, key=lambda r: r.get("cluster", -1)), want):
			if int(got.get("cluster", -1)) != int(exp["cluster"]):
				return False
			if int(got.get("size", -1)) != int(exp["size"]):
				return False
			for key, value in exp.items():
				if key in {"cluster", "size"}:
					continue
				if not close_metric(got.get(key), value, tol=0.15):
					return False
		return True
	if mode == "choose_k":
		if int(answer.get("best_k", -1)) != int(expected["best_k"]):
			return False
		if not close_metric(answer.get("silhouette"), expected["silhouette"], tol=0.08):
			return False
		clusters = answer.get("clusters")
		return isinstance(clusters, list) and len(clusters) == int(expected["best_k"])
	if mode == "pca_compare":
		return (
			int(answer.get("best_k_full", -1)) == int(expected["best_k_full"])
			and int(answer.get("best_k_pca", -1)) == int(expected["best_k_pca"])
			and close_metric(answer.get("silhouette_full"), expected["silhouette_full"], tol=0.1)
			and close_metric(answer.get("silhouette_pca"), expected["silhouette_pca"], tol=0.1)
			and name_match(answer.get("better_space"), expected["better_space"])
		)
	return False
