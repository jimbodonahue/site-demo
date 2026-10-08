from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from apps.exercises.content import load_prompt, render_prompt

REGIONS = ["north", "south", "east", "west"]
STATUSES = ["active", "inactive"]
BRANDS = ["NordicHome", "BrightBean", "SummitGear", "CedarLine", "HarborCo"]

WORD_TO_INT = {
	"zero": 0,
	"one": 1,
	"two": 2,
	"three": 3,
	"four": 4,
	"five": 5,
	"six": 6,
	"seven": 7,
	"eight": 8,
	"nine": 9,
	"ten": 10,
}
INT_TO_WORD = {value: key for key, value in WORD_TO_INT.items()}

EXPECTED_COLUMNS = [
	"store_id",
	"product_id",
	"brand",
	"units",
	"price",
	"rating",
	"status",
	"region",
]


def build_clean_messy_dataframe(
	rows: int = 48,
	seed: int = 42,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> pd.DataFrame:
	"""Build the canonical cleaned sales table from a Data Zoo sample."""
	from apps.exercises.data_zoo import sample_zoo_dataframe

	sector = str(data_field or topic or "retail").strip().lower() or "retail"
	zoo = sample_zoo_dataframe(
		sector,
		rows=max(24, int(rows)),
		seed=seed,
		dataset_file=(dataset_file or None),
	)
	rng = np.random.default_rng(seed)
	n = len(zoo)

	def _numeric(*candidates: str, low: float, high: float) -> np.ndarray:
		for name in candidates:
			if name in zoo.columns and pd.api.types.is_numeric_dtype(zoo[name]):
				series = pd.to_numeric(zoo[name], errors="coerce")
				if series.notna().any():
					return np.round(series.fillna(series.median()).to_numpy(dtype=float), 2)
		return np.round(rng.uniform(low, high, size=n), 2)

	def _category(*candidates: str, choices: list[str]) -> np.ndarray:
		for name in candidates:
			if name in zoo.columns:
				series = zoo[name].astype(str).fillna(choices[0])
				top = series.value_counts().head(len(choices)).index.tolist()
				if len(top) >= 2:
					return series.where(series.isin(top), top[0]).to_numpy()
		return rng.choice(choices, size=n)

	store_ids = _numeric("store_id", "region", low=1, high=12)
	product_ids = np.arange(1001, 1001 + n)
	if "product_id" in zoo.columns and pd.api.types.is_numeric_dtype(zoo["product_id"]):
		product_ids = pd.to_numeric(zoo["product_id"], errors="coerce").fillna(
			pd.Series(product_ids)
		).astype(int).to_numpy()

	units = _numeric("basket_size", "units", "quantity", "items", low=0, high=10)
	price = _numeric("unit_price", "price", "revenue", low=5.0, high=250.0)
	rating = _numeric("loyalty_score", "rating", "review_score", low=1.0, high=5.0)
	# Scale loyalty-like 0–1 scores into a 1–5 rating.
	if rating.max() <= 1.0:
		rating = np.round(1.0 + 4.0 * np.clip(rating, 0, 1), 1)

	status_source = None
	for name in ("return_flag", "status", "active"):
		if name in zoo.columns:
			status_source = zoo[name]
			break
	if status_source is not None:
		status = np.where(
			pd.to_numeric(status_source, errors="coerce").fillna(0).to_numpy() > 0,
			"inactive",
			"active",
		)
	else:
		status = rng.choice(STATUSES, size=n)

	return pd.DataFrame(
		{
			"store_id": np.clip(store_ids, 1, None).astype(int),
			"product_id": product_ids,
			"brand": _category("channel", "brand", "category", choices=BRANDS),
			"units": np.clip(units, 0, 10).astype(int),
			"price": price,
			"rating": np.clip(rating, 1.0, 5.0),
			"status": status,
			"region": _category("region", choices=REGIONS),
		}
	).sort_values(["product_id", "store_id"]).reset_index(drop=True)


def _ocr_corrupt_number(value: float | int, rng: np.random.Generator) -> str:
	"""Apply a single reversible OCR-style substitution."""
	if isinstance(value, (float, np.floating)) and not float(value).is_integer():
		text = f"{float(value):.2f}"
	else:
		text = str(int(value))

	candidates = []
	mapping = [
		("0", "o"),
		("0", "O"),
		("1", "l"),
		("5", "S"),
		("2", "Z"),
		(".", ","),
	]
	for old, new in mapping:
		if old in text:
			candidates.append((old, new))
	if not candidates:
		return text
	old, new = candidates[int(rng.integers(0, len(candidates)))]
	return text.replace(old, new, 1)


def _add_blank_rows(frame: pd.DataFrame, rng: np.random.Generator, count: int) -> pd.DataFrame:
	if count <= 0:
		return frame
	blanks = pd.DataFrame({column: [np.nan] * count for column in frame.columns})
	combined = pd.concat([frame, blanks], ignore_index=True)
	return combined.sample(frac=1.0, random_state=int(rng.integers(0, 10_000))).reset_index(drop=True)


def _add_duplicate_rows(frame: pd.DataFrame, rng: np.random.Generator, count: int) -> pd.DataFrame:
	if count <= 0 or frame.empty:
		return frame
	idxs = rng.choice(frame.index.to_numpy(), size=min(count, len(frame)), replace=True)
	dupes = frame.loc[idxs].copy()
	return pd.concat([frame, dupes], ignore_index=True)


def _push_header_into_first_row(frame: pd.DataFrame) -> pd.DataFrame:
	header = list(frame.columns.astype(str))
	body = frame.copy()
	body.columns = [f"col_{index}" for index in range(len(body.columns))]
	top = pd.DataFrame([header], columns=body.columns)
	return pd.concat([top, body], ignore_index=True)


def _mix_word_numbers(frame: pd.DataFrame, column: str, rng: np.random.Generator, fraction: float) -> pd.DataFrame:
	out = frame.copy()
	out[column] = out[column].astype(object)
	for index in out.index:
		value = out.at[index, column]
		if pd.isna(value):
			continue
		as_int = int(value)
		if as_int in INT_TO_WORD and rng.random() < fraction:
			# Mix casing so students normalize carefully.
			word = INT_TO_WORD[as_int]
			out.at[index, column] = word.title() if rng.random() < 0.5 else word
	return out


def _stringify_numerics(frame: pd.DataFrame, columns: list[str], rng: np.random.Generator, fraction: float) -> pd.DataFrame:
	out = frame.copy()
	for column in columns:
		out[column] = out[column].astype(object)
		for index in out.index:
			if pd.isna(out.at[index, column]):
				continue
			if rng.random() < fraction:
				out.at[index, column] = str(out.at[index, column])
	return out


def _inject_ocr_errors(frame: pd.DataFrame, columns: list[str], rng: np.random.Generator, fraction: float) -> pd.DataFrame:
	out = frame.copy()
	for column in columns:
		out[column] = out[column].astype(object)
		for index in out.index:
			value = out.at[index, column]
			if pd.isna(value):
				continue
			if rng.random() < fraction:
				try:
					numeric = float(value)
				except (TypeError, ValueError):
					continue
				out.at[index, column] = _ocr_corrupt_number(numeric, rng)
	return out


def _duplicate_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
	out = frame.copy()
	for column in columns:
		if column in out.columns:
			out[f"{column}_dup"] = out[column]
	return out


def _prepare_lookup(clean: pd.DataFrame, join_columns: list[str]) -> pd.DataFrame:
	lookup = clean[["product_id", *join_columns]].drop_duplicates("product_id").reset_index(drop=True)
	return lookup


def prepare_messy_dataset(
	difficulty: str = "easy",
	seed: int = 42,
	rows: int = 48,
	*,
	data_field: str | None = None,
	dataset_file: str | None = None,
	topic: str | None = None,
) -> dict[str, Any]:
	"""Build messy inputs plus the expected cleaned dataframe for evaluation."""
	difficulty_key = (difficulty or "easy").lower().strip()
	if difficulty_key not in {"easy", "medium", "hard"}:
		raise ValueError("Unknown difficulty. Use easy, medium, or hard.")

	rng = np.random.default_rng(seed)
	expected = build_clean_messy_dataframe(
		rows=rows,
		seed=seed,
		data_field=data_field,
		dataset_file=dataset_file,
		topic=topic,
	)
	working = expected.copy()
	df_extra = None
	join_columns: list[str] = []

	# --- Shared easy mess ---
	blank_count = 2 if difficulty_key == "easy" else 3 if difficulty_key == "medium" else 5
	dupe_count = 2 if difficulty_key == "easy" else 3 if difficulty_key == "medium" else 6
	working = _mix_word_numbers(working, "units", rng, fraction=0.45 if difficulty_key == "easy" else 0.55)
	working = _stringify_numerics(
		working,
		["price", "rating", "store_id"],
		rng,
		fraction=0.35 if difficulty_key == "easy" else 0.5,
	)
	# Inconsistent similar labels.
	working["status"] = working["status"].astype(object)
	for index in working.index:
		if rng.random() < 0.25:
			value = str(working.at[index, "status"])
			working.at[index, "status"] = value.upper() if rng.random() < 0.5 else f" {value} "

	if difficulty_key in {"medium", "hard"}:
		ocr_fraction = 0.35 if difficulty_key == "medium" else 0.55
		working = _inject_ocr_errors(working, ["price", "rating", "units"], rng, fraction=ocr_fraction)
		dup_cols = ["price"] if difficulty_key == "medium" else ["price", "rating"]
		working = _duplicate_columns(working, dup_cols)

		join_columns = ["brand", "region"]
		df_extra = _prepare_lookup(expected, join_columns)
		working = working.drop(columns=join_columns)

		if difficulty_key == "hard":
			# Force a type mismatch on the join key.
			working["product_id"] = working["product_id"].astype(object)
			for index in working.index:
				if pd.isna(working.at[index, "product_id"]):
					continue
				working.at[index, "product_id"] = str(int(float(working.at[index, "product_id"])))
			if "status" in working.columns:
				working["status_copy"] = working["status"]

	# Exact duplicate / blank rows after cell-level corruption so copies stay identical.
	working = _add_duplicate_rows(working, rng, dupe_count)
	working = _add_blank_rows(working, rng, blank_count)
	if difficulty_key == "hard":
		working = _add_blank_rows(working, rng, 2)
		working = _add_duplicate_rows(working, rng, 2)

	# Header buried in the first row for all difficulties.
	working = _push_header_into_first_row(working)

	prompt_lines = [
		render_prompt(
			"messy_dataset",
			"base",
			columns=", ".join(EXPECTED_COLUMNS),
		),
	]
	if difficulty_key in {"medium", "hard"}:
		prompt_lines.append(load_prompt("messy_dataset", "ocr_repair"))
		prompt_lines.append(load_prompt("messy_dataset", "drop_dup_columns"))
		prompt_lines.append(
			render_prompt(
				"messy_dataset",
				"join_extra",
				join_columns=", ".join(join_columns),
			)
		)
	if difficulty_key == "hard":
		prompt_lines.append(load_prompt("messy_dataset", "hard_extra"))
	prompt_lines.append(load_prompt("messy_dataset", "word_numbers"))
	prompt_lines.append(load_prompt("messy_dataset", "assign_final"))

	task = {
		"difficulty": difficulty_key,
		"prompt": " ".join(prompt_lines),
		"expected_columns": EXPECTED_COLUMNS,
		"join_columns": join_columns,
		"expected_df": expected,
		"word_to_int": WORD_TO_INT,
	}
	return {
		"df": working,
		"df_extra": df_extra,
		"task": task,
		"expected_df": expected,
	}


def repair_messy_number(value: Any) -> float | int | Any:
	"""Repair common OCR-like numeric typos and parse to int/float when possible."""
	if value is None or (isinstance(value, float) and np.isnan(value)):
		return value
	if isinstance(value, (int, np.integer)):
		return int(value)
	if isinstance(value, (float, np.floating)) and not isinstance(value, bool):
		as_float = float(value)
		return int(as_float) if as_float.is_integer() else as_float

	text = str(value).strip()
	lower = text.lower()
	if lower in WORD_TO_INT:
		return WORD_TO_INT[lower]

	replacements = {
		"o": "0",
		"O": "0",
		"!": "1",
		"l": "1",
		"I": "1",
		"Z": "2",
		"z": "2",
		"S": "5",
		"s": "5",
		",": ".",
	}
	cleaned = str(text).strip()
	for old, new in replacements.items():
		cleaned = cleaned.replace(old, new)
	cleaned = cleaned.strip()
	try:
		number = float(cleaned)
	except ValueError:
		return value
	if number.is_integer():
		return int(number)
	return round(number, 2)


def dataframes_match(result_df: Any, expected_df: Any) -> bool:
	if not isinstance(result_df, pd.DataFrame) or not isinstance(expected_df, pd.DataFrame):
		return False

	left = result_df.copy().reset_index(drop=True)
	right = expected_df.copy().reset_index(drop=True)

	if list(left.columns) != list(right.columns):
		if set(left.columns) == set(right.columns):
			left = left.loc[:, list(right.columns)]
		else:
			return False

	if len(left) != len(right):
		return False

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
					rtol=0,
					atol=1e-6,
					equal_nan=True,
				):
					return False
			else:
				left_text = left_col.astype(str).str.strip().str.lower()
				right_text = right_col.astype(str).str.strip().str.lower()
				if not left_text.equals(right_text):
					return False
		return True
	except Exception:
		return False


def messy_dataset_passes(df: Any, task: dict[str, Any] | None = None) -> bool:
	"""Validate the student's cleaned dataframe against the expected tidy table."""
	expected = (task or {}).get("expected_df")
	if expected is None:
		return False
	if not isinstance(df, pd.DataFrame):
		return False
	# Ignore leftover duplicate-looking columns; require the expected schema.
	try:
		candidate = df.copy()
		expected_columns = list((task or {}).get("expected_columns") or expected.columns)
		if set(expected_columns).issubset(set(candidate.columns)):
			candidate = candidate.loc[:, expected_columns]
		candidate = candidate.sort_values(["product_id", "store_id"]).reset_index(drop=True)
		expected_sorted = expected.sort_values(["product_id", "store_id"]).reset_index(drop=True)
		return dataframes_match(candidate, expected_sorted)
	except Exception:
		return False
