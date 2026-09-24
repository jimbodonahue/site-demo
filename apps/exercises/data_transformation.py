from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

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
	regions = _category_series("region", "market_segment", choices=REGIONS)

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
	codes = series.map(index_map).astype(int).to_numpy()
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

	prompt = (
		f"Split the products into three price bands and keep only {_human_columns(columns)}. "
		f"Create `df0` for prices at or below {low_max}, `df1` for prices strictly between "
		f"{low_max} and {high_min}, and `df2` for prices at or above {high_min}. "
		"Reset each result's index."
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
		df2_prompt = (
			f"`df2` with region_code ({region_map_text}), satisfaction_score "
			"(Very Dissatisfied=1 … Very Satisfied=5), and in_stock_flag (yes→1, no→0)"
		)
	else:
		df2_prompt = (
			"`df2` with region, satisfaction_score (Very Dissatisfied=1 … Very Satisfied=5), "
			"and in_stock_flag (yes→1, no→0)"
		)

	prompt = (
		"Clean and encode the messy categorical fields, preferably with `apply` / `lambda` "
		"(or equivalent Series maps). Create three dataframes:\n"
		"- `df0` with brand, price, and cleaned size "
		"(normalize size_raw to Small/Medium/Large/XL)\n"
		"- `df1` with brand, size_code (Small=1, Medium=2, Large=3, XL=4), and units_sold\n"
		f"- {df2_prompt}\n"
		"Keep row order aligned with `df` and reset each index."
	)
	return {
		"difficulty": "medium",
		"mode": "apply_encoding",
		"prompt": prompt,
		"expected": {"df0": df0, "df1": df1, "df2": df2},
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
	prompt = (
		"Apply more advanced encodings and return three dataframes:\n"
		f"- `df0`: one-hot encode `{encode_col}` (0/1 integer columns named `{encode_col}_…`), "
		"and include product_id and price\n"
		f"- `df1`: binary-encode `region` into bits [{bit_names}] using the fixed category order "
		f"{REGIONS} (index 0..{len(REGIONS) - 1}, bit0 = least significant bit), "
		"and include product_id and units_sold\n"
		"- `df2`: map-based encodings with product_id, size_code "
		"(Small=1…XL=4 after cleaning size_raw), satisfaction_score "
		"(Very Dissatisfied=1 … Very Satisfied=5), and in_stock_flag (yes→1, no→0)\n"
		"Reset each index. One-hot column order may match sorted column names."
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
