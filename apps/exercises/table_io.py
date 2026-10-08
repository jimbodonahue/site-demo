"""Table read/write helpers that avoid pyarrow (too large for size-capped hosts)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

TABLE_SUFFIX = ".csv.gz"
LEGACY_SUFFIXES = (".parquet", ".pkl.gz", ".pkl")


def table_path(path: Path | str) -> Path:
	"""Normalize a zoo/cache path to the lite on-disk format."""
	p = Path(path)
	name = p.name
	if name.endswith(TABLE_SUFFIX):
		return p
	for legacy in LEGACY_SUFFIXES:
		if name.endswith(legacy):
			return p.with_name(name[: -len(legacy)] + TABLE_SUFFIX)
	if p.suffix:
		return p.with_suffix(TABLE_SUFFIX)
	return Path(str(p) + TABLE_SUFFIX)


def _stem(name: str) -> str:
	for suffix in (TABLE_SUFFIX, *LEGACY_SUFFIXES):
		if name.endswith(suffix):
			return name[: -len(suffix)]
	return Path(name).stem


def read_table(path: Path | str) -> pd.DataFrame:
	p = Path(path)
	candidates = [p, table_path(p)]
	# Also try sibling stems with known suffixes
	stem = _stem(p.name)
	for suffix in (TABLE_SUFFIX, *LEGACY_SUFFIXES):
		candidates.append(p.with_name(stem + suffix))

	seen: set[Path] = set()
	for candidate in candidates:
		candidate = Path(candidate)
		if candidate in seen or not candidate.exists():
			continue
		seen.add(candidate)
		name = candidate.name
		if name.endswith(TABLE_SUFFIX) or name.endswith(".csv"):
			return pd.read_csv(candidate)
		if name.endswith(".pkl.gz") or name.endswith(".pkl"):
			return pd.read_pickle(candidate)
		if name.endswith(".parquet"):
			return pd.read_parquet(candidate)
	raise FileNotFoundError(f"No table file found for {p}")


def write_table(df: pd.DataFrame, path: Path | str) -> Path:
	out = table_path(path)
	out.parent.mkdir(parents=True, exist_ok=True)
	df.to_csv(out, index=False, compression="gzip")
	return out
