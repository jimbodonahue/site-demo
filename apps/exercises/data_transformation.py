from __future__ import annotations

import io
import zipfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from apps.exercises.content import render_prompt
from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, ZOO_DATA_DIR

BRANDS = [
	"NordicHome",
	"BrightBean",
	"SummitGear",
	"CedarLine",
	"PixelForge",
	"HarborCo",
]

CATEGORIES = ["kitchen", "outdoors", "electronics", "home", "apparel"]
REGIONS = ["north", "south", "east", "west"]

# Messy size labels students must normalize with apply/lambda.
SIZE_RAW_CHOICES = [
	"S",
	"s",
	"small",
	"Small",
	"M",
	"m",
	"medium",
	"Medium",
	"L",
	"l",
	"large",
	"Large",
	"XL",
	"xl",
	"extra large",
]

SIZE_CANONICAL = {
	"s": "Small",
	"small": "Small",
	"m": "Medium",
	"medium": "Medium",
	"l": "Large",
	"large": "Large",
	"xl": "XL",
	"extra large": "XL",
	"x-large": "XL",
}

SIZE_ORDINAL = {"Small": 1, "Medium": 2, "Large": 3, "XL": 4}

# Hard mode sometimes swaps advanced encoding for a multi-table join drill.
JOIN_HARD_PROBABILITY = 0.5

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OLIST_ZIP_PATH = PROJECT_ROOT / "olist.zip"
OLIST_DIR = ZOO_DATA_DIR / "ecommerce" / "olist"

SATISFACTION_LABELS = [
	"Very Dissatisfied",
	"Dissatisfied",
	"Neutral",
	"Satisfied",
	"Very Satisfied",
]
SATISFACTION_ORDINAL = {label: index + 1 for index, label in enumerate(SATISFACTION_LABELS)}


def _normalize_size_label(value: Any) -> str:
	key = str(value).strip().lower()
	if key not in SIZE_CANONICAL:
		raise ValueError(f"Unknown size label: {value!r}")
	return SIZE_CANONICAL[key]


def build_product_dataframe(
	rows: int = 90,
	seed: int = 42,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> pd.DataFrame:
	"""Build the retail teaching table from a Data Zoo sample.

	Numeric / region / brand-like fields are drawn from the zoo frame when
	possible; size/satisfaction/stock columns remain pedagogical overlays so
	encoding drills stay intact.
	"""
	from apps.exercises.data_zoo import sample_zoo_dataframe

	sector = str(data_field or topic or "retail").strip().lower() or "retail"
	zoo = sample_zoo_dataframe(
		sector,
		rows=max(30, int(rows)),
		seed=seed,
		dataset_file=(dataset_file or None),
	)
	rng = np.random.default_rng(seed)
	n = len(zoo)

	def _numeric_series(*candidates: str, fallback: np.ndarray) -> np.ndarray:
		for name in candidates:
			if name in zoo.columns and pd.api.types.is_numeric_dtype(zoo[name]):
				series = pd.to_numeric(zoo[name], errors="coerce")
				if series.notna().any():
					filled = series.fillna(series.median()).to_numpy()
					return np.round(filled.astype(float), 2)
		return fallback

	def _category_series(*candidates: str, choices: list[str]) -> np.ndarray:
		for name in candidates:
			if name in zoo.columns:
				series = zoo[name].astype(str).fillna("unknown")
				# Keep cardinality manageable for encoding drills.
				top = series.value_counts().head(max(3, len(choices))).index.tolist()
				if len(top) >= 2:
					return series.where(series.isin(top), top[0]).to_numpy()
		return rng.choice(choices, size=n)

	price = _numeric_series(
		"unit_price",
		"price",
		"revenue",
		"charges",
		"payment_value",
		fallback=np.round(rng.uniform(8.0, 220.0, size=n), 2),
	)
	units = _numeric_series(
		"basket_size",
		"units_sold",
		"quantity",
		"items",
		fallback=rng.integers(1, 500, size=n).astype(float),
	)
	brands = _category_series("channel", "brand", "category", "segment", choices=BRANDS)
	categories = _category_series("category", "channel", "segment", choices=CATEGORIES)
	# Region labels must stay within REGIONS — hard mode binary-encodes with that fixed order.
	regions = rng.choice(REGIONS, size=n)

	return pd.DataFrame(
		{
			"product_id": np.arange(1, n + 1),
			"brand": brands,
			"category": categories,
			"price": price,
			"units_sold": np.clip(units, 1, None).astype(int),
			"size_raw": rng.choice(SIZE_RAW_CHOICES, size=n),
			"region": regions,
			"satisfaction": rng.choice(SATISFACTION_LABELS, size=n),
			"in_stock": rng.choice(["yes", "Yes", "YES", "no", "No", "NO"], size=n),
		}
	)


def _price_bands(df: pd.DataFrame) -> tuple[float, float]:
	low_max = float(df["price"].quantile(0.33))
	high_min = float(df["price"].quantile(0.66))
	# Guard against degenerate splits on tiny samples.
	if low_max >= high_min:
		low_max = float(df["price"].median())
		high_min = low_max
	return round(low_max, 2), round(high_min, 2)


def _clean_size_series(series: pd.Series) -> pd.Series:
	return series.map(_normalize_size_label)


def _binary_encode_series(series: pd.Series, categories: list[str]) -> pd.DataFrame:
	"""Encode categories as binary bit columns (ceil(log2(k)) bits)."""
	index_map = {value: index for index, value in enumerate(categories)}
	width = max(1, int(np.ceil(np.log2(max(len(categories), 2)))))
	codes = series.map(index_map).fillna(0).astype(int).to_numpy()
	bits = {}
	for bit in range(width):
		bits[f"region_bit{bit}"] = ((codes >> bit) & 1).astype(int)
	return pd.DataFrame(bits, index=series.index)


def _stock_flag(series: pd.Series) -> pd.Series:
	return series.astype(str).str.strip().str.lower().isin(["yes", "y", "true", "1"]).astype(int)


def _build_easy_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	low_max, high_min = _price_bands(df)
	columns = ["brand", "price", "units_sold"]

	df0 = df.loc[df["price"] <= low_max, columns].copy().reset_index(drop=True)
	df1 = (
		df.loc[(df["price"] > low_max) & (df["price"] < high_min), columns]
		.copy()
		.reset_index(drop=True)
	)
	df2 = df.loc[df["price"] >= high_min, columns].copy().reset_index(drop=True)

	# Occasionally swap mid/high wording by regenerating with alternate column order.
	if rng.random() < 0.35:
		columns = ["price", "brand", "units_sold"]
		df0 = df0.loc[:, columns]
		df1 = df1.loc[:, columns]
		df2 = df2.loc[:, columns]

	prompt = render_prompt(
		"data_transformation",
		"price_bands",
		columns=_human_columns(columns),
		low_max=low_max,
		high_min=high_min,
	)
	return {
		"difficulty": "easy",
		"mode": "price_bands",
		"prompt": prompt,
		"thresholds": {"low_max": low_max, "high_min": high_min},
		"columns": columns,
		"expected": {"df0": df0, "df1": df1, "df2": df2},
	}


def _build_medium_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	"""Encode messy categoricals primarily with apply/lambda-style mappings."""
	size_clean = _clean_size_series(df["size_raw"])
	size_code = size_clean.map(SIZE_ORDINAL).astype(int)
	satisfaction_score = df["satisfaction"].map(SATISFACTION_ORDINAL).astype(int)
	stock_flag = _stock_flag(df["in_stock"])

	# Three related frames so students practice encoding + selecting.
	df0 = pd.DataFrame(
		{
			"brand": df["brand"],
			"price": df["price"],
			"size": size_clean,
		}
	).reset_index(drop=True)

	df1 = pd.DataFrame(
		{
			"brand": df["brand"],
			"size_code": size_code,
			"units_sold": df["units_sold"],
		}
	).reset_index(drop=True)

	df2 = pd.DataFrame(
		{
			"region": df["region"],
			"satisfaction_score": satisfaction_score,
			"in_stock_flag": stock_flag,
		}
	).reset_index(drop=True)

	# Variant: sometimes ask for lambda-friendly region codes in df2 instead of region strings.
	if rng.random() < 0.45:
		region_order = list(rng.permutation(REGIONS))
		region_code = df["region"].map({name: index for index, name in enumerate(region_order)}).astype(int)
		df2 = pd.DataFrame(
			{
				"region_code": region_code,
				"satisfaction_score": satisfaction_score,
				"in_stock_flag": stock_flag,
			}
		).reset_index(drop=True)
		region_map_text = ", ".join(f"'{name}'→{index}" for index, name in enumerate(region_order))
		df2_prompt = render_prompt(
			"data_transformation",
			"df2_region_code",
			region_map_text=region_map_text,
		)
	else:
		df2_prompt = render_prompt("data_transformation", "df2_region_string")

	prompt = render_prompt("data_transformation", "apply_encoding", df2_prompt=df2_prompt)
	return {
		"difficulty": "medium",
		"mode": "apply_encoding",
		"prompt": prompt,
		"expected": {"df0": df0, "df1": df1, "df2": df2},
	}



def _normalize_topic(topic: str | None, data_field: str | None = None) -> str:
	sector = str(data_field or topic or "retail").strip().lower() or "retail"
	if sector not in DATA_SCIENCE_SECTORS:
		return "retail"
	return sector


@lru_cache(maxsize=16)
def _load_olist_csv(name: str) -> pd.DataFrame:
	"""Load one Olist CSV from zoo_data/ecommerce/olist/ or project olist.zip."""
	local = OLIST_DIR / name
	if local.exists():
		return pd.read_csv(local)

	if not OLIST_ZIP_PATH.exists():
		raise FileNotFoundError(
			f"Olist data not found at {local} or {OLIST_ZIP_PATH}. "
			"Place olist.zip in the project root or extract CSVs under zoo_data/ecommerce/olist/."
		)
	with zipfile.ZipFile(OLIST_ZIP_PATH) as zf:
		with zf.open(name) as handle:
			return pd.read_csv(io.BytesIO(handle.read()))


def _join_pair_placeholder(
	topic: str,
	*,
	seed: int,
	rows: int,
	rng: np.random.Generator,
) -> dict[str, Any] | None:
	"""Placeholder for non-ecommerce zoo topics.

	Replace with real multi-table packs (see zoo-topic-dataset-groups.md).
	Returning None keeps hard mode on the existing encoding path.
	"""
	_ = (topic, seed, rows, rng)
	return None


def _build_olist_join_hard(
	*,
	seed: int,
	rows: int,
	rng: np.random.Generator,
) -> dict[str, Any]:
	"""Hard join drill using real Olist order_items + products tables."""
	items = _load_olist_csv("olist_order_items_dataset.csv")
	products = _load_olist_csv("olist_products_dataset.csv")

	items = items.dropna(subset=["product_id", "order_id", "price", "freight_value"]).copy()
	products = products.dropna(subset=["product_id"]).copy()
	products = products[
		["product_id", "product_category_name", "product_weight_g"]
	].drop_duplicates("product_id")

	merged_keys = items.merge(products[["product_id"]], on="product_id", how="inner")
	target_n = max(30, int(rows))
	if len(merged_keys) < target_n:
		sample = merged_keys.sample(n=len(merged_keys), random_state=seed).reset_index(drop=True)
	else:
		sample = merged_keys.sample(n=target_n, random_state=seed).reset_index(drop=True)

	df = sample[
		["order_id", "order_item_id", "product_id", "price", "freight_value"]
	].copy().reset_index(drop=True)
	df["price"] = pd.to_numeric(df["price"], errors="coerce").astype(float)
	df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce").astype(float)

	needed_ids = set(df["product_id"].astype(str))
	df_extra = (
		products[products["product_id"].astype(str).isin(needed_ids)]
		.copy()
		.reset_index(drop=True)
	)
	df_extra["product_weight_g"] = pd.to_numeric(df_extra["product_weight_g"], errors="coerce")
	df_extra["product_category_name"] = (
		df_extra["product_category_name"].fillna("unknown").astype(str).str.strip()
	)

	joined = df.merge(df_extra, on="product_id", how="left")
	weight_threshold = float(joined["product_weight_g"].median(skipna=True))
	if np.isnan(weight_threshold):
		weight_threshold = 0.0
	weight_threshold = round(weight_threshold, 2)

	df0 = joined[
		["order_id", "product_id", "price", "product_category_name"]
	].copy().reset_index(drop=True)

	one_hot = pd.get_dummies(joined["product_category_name"], prefix="category")
	one_hot = one_hot.reindex(sorted(one_hot.columns), axis=1).astype(int)
	df1 = pd.concat(
		[
			joined[["product_id", "price"]].reset_index(drop=True),
			one_hot.reset_index(drop=True),
		],
		axis=1,
	)

	df2 = pd.DataFrame(
		{
			"product_id": joined["product_id"],
			"freight_value": joined["freight_value"],
			"heavy_item": (
				joined["product_weight_g"].fillna(0).astype(float) >= weight_threshold
			).astype(int),
		}
	).reset_index(drop=True)

	prompt = render_prompt(
		"data_transformation",
		"join_transform",
		weight_threshold=weight_threshold,
	)
	_ = rng
	return {
		"df": df,
		"df_extra": df_extra,
		"task": {
			"difficulty": "hard",
			"mode": "join_transform",
			"prompt": prompt,
			"join_key": "product_id",
			"weight_threshold": weight_threshold,
			"expected": {"df0": df0, "df1": df1, "df2": df2},
		},
	}


# Per-topic hard-mode join builders. Only ecommerce is wired (Olist); others are stubs.
JOIN_PAIR_BUILDERS: dict[str, Callable[..., dict[str, Any] | None]] = {
	sector: _join_pair_placeholder for sector in DATA_SCIENCE_SECTORS
}
JOIN_PAIR_BUILDERS["ecommerce"] = _build_olist_join_hard  # type: ignore[assignment]


def _try_prepare_join_hard(
	topic: str,
	*,
	seed: int,
	rows: int,
	rng: np.random.Generator,
) -> dict[str, Any] | None:
	builder = JOIN_PAIR_BUILDERS.get(topic, _join_pair_placeholder)
	if builder is _join_pair_placeholder:
		return None
	try:
		prepared = _build_olist_join_hard(seed=seed, rows=rows, rng=rng)
	except FileNotFoundError:
		return None
	if not prepared:
		return None
	task = prepared.get("task") or {}
	expected = task.get("expected") or {}
	if not all(name in expected and len(expected[name]) > 0 for name in ("df0", "df1", "df2")):
		return None
	return {
		"df": prepared["df"],
		"df_extra": prepared.get("df_extra"),
		"task": task,
		"df0": None,
		"df1": None,
		"df2": None,
	}


def _build_hard_task(df: pd.DataFrame, rng: np.random.Generator) -> dict[str, Any]:
	"""Advanced encodings: one-hot, binary bits, and explicit maps."""
	encode_col = str(rng.choice(["brand", "category"]))
	categories = sorted(df[encode_col].unique())
	one_hot = pd.get_dummies(df[encode_col], prefix=encode_col)
	# Stable column order for expected frames.
	one_hot = one_hot.reindex(sorted(one_hot.columns), axis=1).astype(int)
	df0 = pd.concat(
		[df[["product_id", "price"]].reset_index(drop=True), one_hot.reset_index(drop=True)],
		axis=1,
	)

	region_bits = _binary_encode_series(df["region"], REGIONS)
	df1 = pd.concat(
		[
			df[["product_id", "units_sold"]].reset_index(drop=True),
			region_bits.reset_index(drop=True),
		],
		axis=1,
	)

	satisfaction_score = df["satisfaction"].map(SATISFACTION_ORDINAL).astype(int)
	size_code = _clean_size_series(df["size_raw"]).map(SIZE_ORDINAL).astype(int)
	df2 = pd.DataFrame(
		{
			"product_id": df["product_id"],
			"size_code": size_code,
			"satisfaction_score": satisfaction_score,
			"in_stock_flag": _stock_flag(df["in_stock"]),
		}
	).reset_index(drop=True)

	bit_names = ", ".join(region_bits.columns)
	prompt = render_prompt(
		"data_transformation",
		"advanced_encoding",
		encode_col=encode_col,
		bit_names=bit_names,
		regions=REGIONS,
		region_max=len(REGIONS) - 1,
	)
	return {
		"difficulty": "hard",
		"mode": "advanced_encoding",
		"prompt": prompt,
		"one_hot_column": encode_col,
		"expected": {"df0": df0, "df1": df1, "df2": df2},
	}


def _human_columns(columns: list[str]) -> str:
	if len(columns) == 1:
		return columns[0]
	if len(columns) == 2:
		return f"{columns[0]} and {columns[1]}"
	return ", ".join(columns[:-1]) + f", and {columns[-1]}"


def prepare_data_transformation(
	difficulty: str = "easy",
	seed: int = 42,
	rows: int = 90,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
	join_probability: float = JOIN_HARD_PROBABILITY,
) -> dict[str, Any]:
	"""Build notebook inputs for the Data Transformation exercise.

	On hard mode, roughly ``join_probability`` of ecommerce attempts use a real
	Olist join drill (`df` + `df_extra`). Other topics have join placeholders
	and keep the advanced-encoding path until packs are wired.
	"""
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		difficulty_key = "easy"
	sector = _normalize_topic(topic, data_field)
	rng = np.random.default_rng(int(seed))

	# Join drills are only implemented for ecommerce (Olist) today; other topics
	# keep placeholder builders and stay on the encoding path.
	if (
		difficulty_key == "hard"
		and JOIN_PAIR_BUILDERS.get(sector, _join_pair_placeholder) is not _join_pair_placeholder
		and float(rng.random()) < float(join_probability)
	):
		joined = _try_prepare_join_hard(sector, seed=int(seed), rows=int(rows), rng=rng)
		if joined is not None:
			return joined

	df = build_product_dataframe(
		rows=rows,
		seed=seed,
		data_field=sector,
		dataset_file=dataset_file,
		topic=sector,
	)
	task = generate_data_transformation_task(df, difficulty=difficulty_key, seed=seed)
	return {
		"df": df,
		"df_extra": None,
		"task": task,
		"df0": None,
		"df1": None,
		"df2": None,
	}


def generate_data_transformation_task(
	df: pd.DataFrame,
	difficulty: str = "easy",
	seed: int = 42,
) -> dict[str, Any]:
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		raise ValueError("Unknown difficulty. Use easy, medium, or hard.")

	builders = {
		"easy": _build_easy_task,
		"medium": _build_medium_task,
		"hard": _build_hard_task,
	}
	last_error: Exception | None = None
	for attempt in range(12):
		attempt_rng = np.random.default_rng(int(seed) + attempt * 89)
		try:
			task = builders[difficulty_key](df, attempt_rng)
			expected = task["expected"]
			if all(len(expected[name]) > 0 for name in ("df0", "df1", "df2")):
				return task
		except Exception as exc:  # pragma: no cover
			last_error = exc
			continue
	if last_error:
		raise last_error
	return _build_easy_task(df, np.random.default_rng(seed))


def dataframes_match(result_df: Any, expected_df: Any) -> bool:
	if not isinstance(result_df, pd.DataFrame) or not isinstance(expected_df, pd.DataFrame):
		return False

	left = result_df.copy().reset_index(drop=True)
	right = expected_df.copy().reset_index(drop=True)

	if list(left.columns) != list(right.columns):
		if set(left.columns) == set(right.columns):
			left = left.loc[:, right.columns]
		else:
			return False

	if len(left) != len(right):
		return False

	# Allow float tolerance and bool/int equivalence for encoded flags.
	try:
		for column in right.columns:
			left_col = left[column]
			right_col = right[column]
			if pd.api.types.is_numeric_dtype(right_col) or pd.api.types.is_numeric_dtype(left_col):
				left_num = pd.to_numeric(left_col, errors="coerce")
				right_num = pd.to_numeric(right_col, errors="coerce")
				if not np.allclose(
					left_num.to_numpy(dtype=float),
					right_num.to_numpy(dtype=float),
					equal_nan=True,
				):
					return False
			else:
				if not left_col.astype(str).equals(right_col.astype(str)):
					return False
		return True
	except Exception:
		return left.equals(right)


def data_transformation_passes(
	task: dict[str, Any],
	df0: Any = None,
	df1: Any = None,
	df2: Any = None,
) -> bool:
	expected = (task or {}).get("expected") or {}
	frames = {"df0": df0, "df1": df1, "df2": df2}
	for name, frame in frames.items():
		if name not in expected:
			return False
		if not dataframes_match(frame, expected[name]):
			return False
	return True
