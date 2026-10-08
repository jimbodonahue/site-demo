"""Typed grading engine: rubric sections, soft/hard modes, and semantic checks."""

from __future__ import annotations

import ast
import math
import re
from copy import deepcopy
from typing import Any, Callable

import numpy as np
import pandas as pd

SECTION_CORE = "core"
SECTION_APPROACH = "approach"
SECTION_BONUS = "bonus"
SECTION_REFLECTION = "reflection"

BAND_PASS = "pass"
BAND_PASS_WITH_ISSUES = "pass_with_issues"
BAND_INCOMPLETE = "incomplete"

MODE_RUN = "run"
MODE_EVALUATE = "evaluate"

VISIBILITY_VISIBLE = "visible"
VISIBILITY_HIDDEN = "hidden"

ANSWER_POLICY_SHOW = "show"
ANSWER_POLICY_OFFER = "offer"
ANSWER_POLICY_HIDE = "hide"


def _as_list(value: Any) -> list[Any]:
	if value is None:
		return []
	if isinstance(value, list):
		return value
	return [value]


def _resolve_path(namespace: dict[str, Any], path: str | None) -> Any:
	"""Resolve dotted/bracket paths like ``task.expected`` or ``task['expected_df']``."""
	if not path:
		return None
	text = str(path).strip()
	if not text:
		return None
	# Support both task.expected and task["expected"]
	token_re = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|\[['\"]([^'\"]+)['\"]\]|\.([A-Za-z_][A-Za-z0-9_]*)")
	parts: list[str] = []
	if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", text):
		parts = [text]
	else:
		first = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$", text)
		if not first:
			return namespace.get(text)
		parts.append(first.group(1))
		rest = first.group(2)
		for match in re.finditer(r"\[['\"]([^'\"]+)['\"]\]|\.([A-Za-z_][A-Za-z0-9_]*)", rest):
			parts.append(match.group(1) or match.group(2))
	current: Any = namespace
	for part in parts:
		if isinstance(current, dict):
			if part not in current:
				return None
			current = current[part]
		else:
			if not hasattr(current, part):
				return None
			current = getattr(current, part)
	return current


def _get_expected(spec: dict[str, Any], namespace: dict[str, Any]) -> Any:
	if "expected" in spec:
		return spec.get("expected")
	return _resolve_path(namespace, spec.get("expected_from"))


def _get_variable(namespace: dict[str, Any], name: str | None) -> Any:
	if not name:
		return None
	return namespace.get(name)


def difficulty_from_namespace(namespace: dict[str, Any] | None) -> str:
	data = namespace.get("data") if isinstance((namespace or {}).get("data"), dict) else {}
	difficulty = str(data.get("selected_feature") or data.get("difficulty") or "easy").lower().strip()
	if difficulty not in {"easy", "medium", "hard"}:
		return "easy"
	return difficulty


def resolve_answer_reveal(difficulty: str, reveal_requested: bool = False) -> dict[str, Any]:
	"""Difficulty-gated correct-answer visibility (never solution code).

	easy → always show the correct answer
	medium → offer to show; include only when requested
	hard → never show the correct answer
	"""
	level = (difficulty or "easy").lower().strip()
	if level == "easy":
		return {"policy": ANSWER_POLICY_SHOW, "revealed": True, "can_reveal": False}
	if level == "medium":
		revealed = bool(reveal_requested)
		return {"policy": ANSWER_POLICY_OFFER, "revealed": revealed, "can_reveal": not revealed}
	return {"policy": ANSWER_POLICY_HIDE, "revealed": False, "can_reveal": False}


def display_value(value: Any, *, max_rows: int = 5, max_chars: int = 800) -> str:
	"""Human-readable value preview for feedback (not executable solution code)."""
	if value is None:
		return "None"
	if isinstance(value, pd.DataFrame):
		if value.empty:
			return "(empty DataFrame)"
		preview = value.head(max_rows)
		try:
			text = preview.to_string(index=False)
		except Exception:
			text = repr(preview)
		extra = ""
		if len(value) > max_rows:
			extra = f"\n… ({len(value)} rows × {len(value.columns)} columns)"
		text = text + extra
		return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
	if isinstance(value, dict):
		parts = []
		for key, item in list(value.items())[:12]:
			parts.append(f"{key}: {display_value(item, max_rows=2, max_chars=100)}")
		text = "{ " + "; ".join(parts) + ("; …" if len(value) > 12 else "") + " }"
		return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
	if isinstance(value, (list, tuple, set)):
		try:
			seq = list(value)
		except Exception:
			return repr(value)[:max_chars]
		text = repr(seq[:20]) + ("…" if len(seq) > 20 else "")
		return text if len(text) <= max_chars else text[: max_chars - 1] + "…"
	if isinstance(value, (np.bool_, bool)):
		return str(bool(value))
	if isinstance(value, (np.integer,)):
		return str(int(value))
	if isinstance(value, (np.floating, float)):
		try:
			return repr(float(value))
		except Exception:
			return str(value)
	text = repr(value)
	return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def _json_safe(value: Any) -> Any:
	"""JSON-friendly form of a value for API payloads."""
	if value is None or isinstance(value, (bool, int, float, str)):
		return value
	if isinstance(value, (np.bool_,)):
		return bool(value)
	if isinstance(value, (np.integer,)):
		return int(value)
	if isinstance(value, (np.floating,)):
		try:
			number = float(value)
		except Exception:
			return display_value(value)
		if math.isnan(number) or math.isinf(number):
			return str(number)
		return number
	if isinstance(value, pd.DataFrame):
		head = value.head(5)
		try:
			records = head.astype(object).where(pd.notnull(head), None).to_dict(orient="records")
		except Exception:
			records = []
		return {
			"_type": "dataframe",
			"shape": [int(value.shape[0]), int(value.shape[1])],
			"columns": [str(c) for c in value.columns],
			"preview": records,
			"display": display_value(value),
		}
	if isinstance(value, dict):
		return {str(k): _json_safe(v) for k, v in list(value.items())[:40]}
	if isinstance(value, (list, tuple)):
		return [_json_safe(v) for v in list(value)[:40]]
	return display_value(value)


# ---------------------------------------------------------------------------
# Semantic equality helpers
# ---------------------------------------------------------------------------

def values_equal(
	actual: Any,
	expected: Any,
	*,
	atol: float = 1e-6,
	rtol: float = 1e-6,
	normalize_strings: bool = False,
) -> bool:
	if actual is None and expected is None:
		return True
	if actual is None or expected is None:
		return False
	if isinstance(expected, (bool, np.bool_)) or isinstance(actual, (bool, np.bool_)):
		try:
			return bool(actual) is bool(expected)
		except Exception:
			return False
	if isinstance(expected, str) or isinstance(actual, str):
		left = str(actual)
		right = str(expected)
		if normalize_strings:
			left = left.strip().lower()
			right = right.strip().lower()
		return left == right
	if isinstance(expected, (int, np.integer)) and not isinstance(expected, (bool, np.bool_)):
		try:
			return int(actual) == int(expected)
		except Exception:
			return False
	if isinstance(expected, (float, np.floating)) or isinstance(actual, (float, np.floating)):
		try:
			return math.isclose(float(actual), float(expected), rel_tol=rtol, abs_tol=atol)
		except Exception:
			return False
	if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple, set, np.ndarray, pd.Series)):
		try:
			left = list(actual)
			right = list(expected)
		except Exception:
			return False
		if len(left) != len(right):
			return False
		return all(
			values_equal(a, b, atol=atol, rtol=rtol, normalize_strings=normalize_strings)
			for a, b in zip(left, right)
		)
	if isinstance(expected, set):
		try:
			return set(actual) == set(expected)
		except Exception:
			return False
	try:
		return bool(actual == expected)
	except Exception:
		return False


def frame_equal(
	actual: Any,
	expected: Any,
	*,
	ignore_index: bool = True,
	ignore_column_order: bool = True,
	atol: float = 1e-6,
	rtol: float = 1e-6,
) -> bool:
	report = frame_diff(
		actual,
		expected,
		ignore_index=ignore_index,
		ignore_column_order=ignore_column_order,
		atol=atol,
		rtol=rtol,
	)
	return bool(report.get("equal"))


def frame_diff(
	actual: Any,
	expected: Any,
	*,
	ignore_index: bool = True,
	ignore_column_order: bool = True,
	atol: float = 1e-6,
	rtol: float = 1e-6,
	preview_rows: int = 3,
) -> dict[str, Any]:
	if not isinstance(actual, pd.DataFrame) or not isinstance(expected, pd.DataFrame):
		return {
			"equal": False,
			"reason": "not_dataframe",
			"message": "Expected a pandas DataFrame.",
			"next_action": "Assign your result to a DataFrame variable before evaluating.",
		}
	left = actual.copy()
	right = expected.copy()
	if ignore_index:
		left = left.reset_index(drop=True)
		right = right.reset_index(drop=True)

	missing_cols = [c for c in right.columns if c not in left.columns]
	extra_cols = [c for c in left.columns if c not in right.columns]
	if missing_cols or (extra_cols and not ignore_column_order and list(left.columns) != list(right.columns)):
		return {
			"equal": False,
			"reason": "columns",
			"missing_columns": missing_cols,
			"extra_columns": extra_cols,
			"message": "Column layout does not match yet.",
			"next_action": (
				f"Add missing column(s): {', '.join(map(str, missing_cols))}."
				if missing_cols
				else "Drop extra columns and keep only the requested fields."
			),
		}
	if set(left.columns) != set(right.columns):
		return {
			"equal": False,
			"reason": "columns",
			"missing_columns": missing_cols,
			"extra_columns": extra_cols,
			"message": "Column sets differ.",
			"next_action": (
				f"Include {', '.join(map(str, missing_cols))}."
				if missing_cols
				else f"Remove unexpected column(s): {', '.join(map(str, extra_cols))}."
			),
		}
	if ignore_column_order:
		left = left.loc[:, list(right.columns)]
	elif list(left.columns) != list(right.columns):
		return {
			"equal": False,
			"reason": "column_order",
			"message": "Columns are present but ordered differently.",
			"next_action": f"Reorder columns to: {list(right.columns)}.",
		}

	if len(left) != len(right):
		return {
			"equal": False,
			"reason": "shape",
			"actual_rows": len(left),
			"expected_rows": len(right),
			"message": f"Row count differs ({len(left)} vs {len(right)}).",
			"next_action": "Adjust your filter/sort so you keep the expected number of rows.",
		}

	# Dtype-tolerant compare with float tolerance.
	mismatches = 0
	first_rows: list[dict[str, Any]] = []
	for col in right.columns:
		a = left[col]
		b = right[col]
		try:
			if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
				a_vals = pd.to_numeric(a, errors="coerce")
				b_vals = pd.to_numeric(b, errors="coerce")
				close = np.isclose(
					a_vals.to_numpy(dtype=float),
					b_vals.to_numpy(dtype=float),
					atol=atol,
					rtol=rtol,
					equal_nan=True,
				)
				bad_idx = np.where(~close)[0]
			else:
				a_norm = a.astype(str).fillna("")
				b_norm = b.astype(str).fillna("")
				bad_idx = np.where((a_norm != b_norm).to_numpy())[0]
		except Exception:
			try:
				bad_idx = np.where((a != b).fillna(True).to_numpy())[0]
			except Exception:
				return {
					"equal": False,
					"reason": "compare_error",
					"message": f"Could not compare column `{col}`.",
					"next_action": f"Check dtypes and values in `{col}`.",
				}
		if len(bad_idx):
			mismatches += int(len(bad_idx))
			for idx in bad_idx[:preview_rows]:
				if len(first_rows) >= preview_rows:
					break
				actual_val = None if pd.isna(a.iloc[idx]) else a.iloc[idx]
				expected_val = None if pd.isna(b.iloc[idx]) else b.iloc[idx]
				first_rows.append(
					{
						"row": int(idx),
						"column": str(col),
						"actual": _json_safe(actual_val),
						"expected": _json_safe(expected_val),
						"expected_hidden": True,
					}
				)

	if mismatches:
		return {
			"equal": False,
			"reason": "values",
			"mismatch_count": mismatches,
			"preview": first_rows,
			"message": f"{mismatches} cell value(s) differ from the expected table.",
			"next_action": "Inspect filters, encodings, and sorting — start with the first mismatched rows.",
		}
	return {"equal": True, "message": "DataFrames match.", "next_action": ""}


def series_close(actual: Any, expected: Any, *, atol: float = 1e-6, rtol: float = 1e-6) -> bool:
	try:
		left = pd.Series(actual).reset_index(drop=True)
		right = pd.Series(expected).reset_index(drop=True)
	except Exception:
		return False
	if len(left) != len(right):
		return False
	try:
		return bool(
			np.allclose(
				pd.to_numeric(left, errors="coerce").to_numpy(dtype=float),
				pd.to_numeric(right, errors="coerce").to_numpy(dtype=float),
				atol=atol,
				rtol=rtol,
				equal_nan=True,
			)
		)
	except Exception:
		return False


# ---------------------------------------------------------------------------
# AST process signals
# ---------------------------------------------------------------------------

def analyze_process_signals(cell_sources: list[str]) -> dict[str, Any]:
	methods: set[str] = set()
	names: set[str] = set()
	joined = "\n".join(cell_sources or [])
	for source in cell_sources or []:
		try:
			tree = ast.parse(source or "")
		except SyntaxError:
			continue
		for node in ast.walk(tree):
			if isinstance(node, ast.Call):
				func = node.func
				if isinstance(func, ast.Attribute):
					methods.add(func.attr)
				elif isinstance(func, ast.Name):
					methods.add(func.id)
					names.add(func.id)
			elif isinstance(node, ast.Attribute):
				methods.add(node.attr)
			elif isinstance(node, ast.Name):
				names.add(node.id)
	return {"methods": sorted(methods), "names": sorted(names), "source": joined}


# ---------------------------------------------------------------------------
# Individual graders
# ---------------------------------------------------------------------------

def _base_result(
	spec: dict[str, Any],
	*,
	passed: bool,
	message: str,
	next_action: str = "",
	details: dict[str, Any] | None = None,
	issues: bool = False,
) -> dict[str, Any]:
	return {
		"id": spec.get("id") or spec.get("type") or "check",
		"type": spec.get("type") or "check",
		"section": spec.get("section") or SECTION_CORE,
		"visibility": spec.get("visibility") or VISIBILITY_VISIBLE,
		"passed": bool(passed),
		"issues": bool(issues),
		"message": message,
		"next_action": next_action if not passed else "",
		"hint": spec.get("hint") or "",
		"details": details or {},
		"strategy": spec.get("strategy"),
	}


def _grade_required_variable(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable") or spec.get("name")
	has = name in namespace
	return _base_result(
		spec,
		passed=has,
		message=f"`{name}` is available." if has else f"Missing variable `{name}`.",
		next_action=spec.get("next_action")
		or (f"Create a variable named `{name}` with your result." if name else "Define the required variable."),
	)


def _grade_equals(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable") or spec.get("name")
	actual = _get_variable(namespace, name)
	expected = _get_expected(spec, namespace)
	ok = values_equal(
		actual,
		expected,
		atol=float(spec.get("atol", 1e-6)),
		rtol=float(spec.get("rtol", 1e-6)),
		normalize_strings=bool(spec.get("normalize_strings", False)),
	)
	if ok:
		message = "Value matched."
	else:
		message = f"`{name}` is incorrect (got {display_value(actual)})."
	return _base_result(
		spec,
		passed=ok,
		message=message,
		next_action=spec.get("next_action") or f"Recompute `{name}` from the dataframe — avoid hard-coding.",
		details={
			"actual": _json_safe(actual),
			"expected": _json_safe(expected),
			"actual_display": display_value(actual),
			"expected_display": display_value(expected),
		},
	)


def _grade_frame_equal(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable") or "df"
	actual = _get_variable(namespace, name)
	expected = _get_expected(spec, namespace)
	report = frame_diff(
		actual,
		expected,
		ignore_index=bool(spec.get("ignore_index", True)),
		ignore_column_order=bool(spec.get("ignore_column_order", True)),
		atol=float(spec.get("atol", 1e-6)),
		rtol=float(spec.get("rtol", 1e-6)),
	)
	details = {k: v for k, v in report.items() if k not in {"equal"}}
	if not report.get("equal"):
		details["actual_display"] = display_value(actual)
		details["expected_display"] = display_value(expected)
		details["expected"] = _json_safe(expected)
	return _base_result(
		spec,
		passed=bool(report.get("equal")),
		message=report.get("message") or ("Tables match." if report.get("equal") else "Tables differ."),
		next_action=spec.get("next_action") or report.get("next_action") or "",
		details=details,
	)


def _grade_series_close(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable")
	actual = _get_variable(namespace, name)
	expected = _get_expected(spec, namespace)
	ok = series_close(
		actual,
		expected,
		atol=float(spec.get("atol", 1e-6)),
		rtol=float(spec.get("rtol", 1e-6)),
	)
	return _base_result(
		spec,
		passed=ok,
		message="Series matched." if ok else f"`{name}` is incorrect (got {display_value(actual)}).",
		next_action=spec.get("next_action") or f"Check calculations that produce `{name}`.",
		details={
			"actual_display": display_value(actual),
			"expected_display": display_value(expected),
			"expected": _json_safe(expected),
		},
	)


def _grade_set_equal(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable")
	actual = _get_variable(namespace, name)
	expected = _get_expected(spec, namespace)
	try:
		ok = set(actual) == set(expected)
	except Exception:
		ok = False
	return _base_result(
		spec,
		passed=ok,
		message="Sets matched." if ok else f"`{name}` is incorrect (got {display_value(actual)}).",
		next_action=spec.get("next_action") or f"Ensure `{name}` includes exactly the required items.",
		details={
			"actual_display": display_value(actual),
			"expected_display": display_value(expected),
			"expected": _json_safe(expected),
		},
	)


def _grade_contains_columns(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable") or "df"
	frame = _get_variable(namespace, name)
	columns = list(spec.get("columns") or _get_expected(spec, namespace) or [])
	if not isinstance(frame, pd.DataFrame):
		return _base_result(
			spec,
			passed=False,
			message=f"`{name}` should be a DataFrame.",
			next_action=f"Assign a DataFrame to `{name}`.",
		)
	missing = [c for c in columns if c not in frame.columns]
	ok = not missing
	return _base_result(
		spec,
		passed=ok,
		message="Required columns present." if ok else f"Missing columns: {', '.join(map(str, missing))}.",
		next_action=spec.get("next_action")
		or (f"Add column(s): {', '.join(map(str, missing))}." if missing else ""),
		details={"missing_columns": missing},
	)


def _grade_shape(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable") or "df"
	frame = _get_variable(namespace, name)
	if not hasattr(frame, "shape"):
		return _base_result(
			spec,
			passed=False,
			message=f"`{name}` has no shape.",
			next_action=f"Assign a DataFrame/array to `{name}`.",
		)
	rows = spec.get("rows")
	cols = spec.get("cols")
	expected = _get_expected(spec, namespace)
	if isinstance(expected, (list, tuple)) and len(expected) == 2:
		rows = expected[0] if rows is None else rows
		cols = expected[1] if cols is None else cols
	actual_rows, actual_cols = frame.shape[0], frame.shape[1] if len(frame.shape) > 1 else 1
	ok = True
	parts = []
	if rows is not None and int(actual_rows) != int(rows):
		ok = False
		parts.append(f"rows {actual_rows}≠{rows}")
	if cols is not None and int(actual_cols) != int(cols):
		ok = False
		parts.append(f"cols {actual_cols}≠{cols}")
	return _base_result(
		spec,
		passed=ok,
		message="Shape matched." if ok else f"Shape mismatch ({', '.join(parts)}).",
		next_action=spec.get("next_action") or "Adjust filtering or column selection to hit the expected shape.",
	)


def _grade_dtype(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	name = spec.get("variable") or "df"
	frame = _get_variable(namespace, name)
	column = spec.get("column")
	kind = (spec.get("kind") or "numeric").lower()
	if not isinstance(frame, pd.DataFrame) or column not in getattr(frame, "columns", []):
		return _base_result(
			spec,
			passed=False,
			message=f"Column `{column}` not found on `{name}`.",
			next_action=f"Ensure `{name}` includes `{column}`.",
		)
	series = frame[column]
	if kind == "numeric":
		ok = bool(pd.api.types.is_numeric_dtype(series))
	elif kind in {"string", "object"}:
		ok = bool(pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series))
	elif kind == "bool":
		ok = bool(pd.api.types.is_bool_dtype(series))
	else:
		ok = str(series.dtype) == kind
	return _base_result(
		spec,
		passed=ok,
		message=f"`{column}` dtype ok." if ok else f"`{column}` should be {kind}.",
		next_action=spec.get("next_action") or f"Convert `{column}` to a {kind} dtype.",
	)


def _invariant_no_nulls(frame: Any) -> tuple[bool, str, str]:
	if not isinstance(frame, pd.DataFrame):
		return False, "Expected a DataFrame.", "Assign a DataFrame before checking nulls."
	n = int(frame.isna().sum().sum())
	if n == 0:
		return True, "No missing values remain.", ""
	return False, f"{n} missing value(s) remain.", "Fill or drop remaining NA values."


def _invariant_no_duplicates(frame: Any) -> tuple[bool, str, str]:
	if not isinstance(frame, pd.DataFrame):
		return False, "Expected a DataFrame.", "Assign a DataFrame before checking duplicates."
	n = int(frame.duplicated().sum())
	if n == 0:
		return True, "No duplicate rows.", ""
	return False, f"{n} duplicate row(s) remain.", "Drop duplicate rows."


def _invariant_observed_unchanged(
	frame: Any,
	baseline: Any,
	target: str,
	missing_index: Any,
) -> tuple[bool, str, str]:
	if not isinstance(frame, pd.DataFrame) or not isinstance(baseline, pd.DataFrame):
		return False, "Baseline/frame unavailable.", "Keep non-missing rows unchanged."
	if target not in frame.columns or target not in baseline.columns:
		return False, f"Missing target column `{target}`.", f"Keep column `{target}` in your frame."
	try:
		observed = baseline.index.difference(missing_index)
		left = frame.loc[observed, target]
		right = baseline.loc[observed, target]
		ok = bool(left.equals(right))
	except Exception:
		ok = False
	if ok:
		return True, "Non-missing rows unchanged.", ""
	return False, "Some originally observed values changed.", "Only fill NA cells; leave observed values alone."


def _grade_invariant(spec: dict[str, Any], namespace: dict[str, Any], **kwargs) -> dict[str, Any]:
	name = spec.get("name") or spec.get("invariant")
	variable = spec.get("variable") or "df"
	frame = _get_variable(namespace, variable)
	if name == "no_nulls":
		ok, message, next_action = _invariant_no_nulls(frame)
	elif name == "no_duplicates":
		ok, message, next_action = _invariant_no_duplicates(frame)
	elif name == "observed_unchanged":
		baseline = _get_variable(namespace, spec.get("baseline") or "df_baseline")
		target = _get_variable(namespace, spec.get("target") or "target") or spec.get("target_column")
		meta = namespace.get("data") if isinstance(namespace.get("data"), dict) else {}
		missing_index = kwargs.get("missing_index")
		ok, message, next_action = _invariant_observed_unchanged(frame, baseline, str(target), missing_index or [])
	elif name == "expression":
		expression = spec.get("expression") or ""
		try:
			ok = bool(eval(expression, namespace, namespace))  # noqa: S307 — sandboxed exercise namespace
			message = "Invariant held." if ok else "Invariant failed."
			next_action = spec.get("next_action") or "Adjust your solution so the invariant holds."
		except Exception as exc:
			ok = False
			message = f"Invariant error: {exc}"
			next_action = spec.get("next_action") or "Fix errors preventing the invariant check."
	else:
		ok = False
		message = f"Unknown invariant `{name}`."
		next_action = "Update the exercise grader configuration."
	return _base_result(
		spec,
		passed=ok,
		message=message,
		next_action=spec.get("next_action") or next_action,
	)


def _grade_ast_process(
	spec: dict[str, Any],
	namespace: dict[str, Any],
	*,
	cell_sources: list[str] | None = None,
	**_kwargs,
) -> dict[str, Any]:
	analysis = analyze_process_signals(cell_sources or [])
	methods = set(analysis.get("methods") or [])
	require_any = set(spec.get("require_any") or spec.get("require_any_methods") or [])
	require_all = set(spec.get("require_all") or [])
	forbid = set(spec.get("forbid") or [])
	ok = True
	parts = []
	if require_any and not (methods & require_any):
		ok = False
		parts.append(f"use one of: {', '.join(sorted(require_any))}")
	if require_all and not require_all.issubset(methods):
		ok = False
		missing = sorted(require_all - methods)
		parts.append(f"also use: {', '.join(missing)}")
	if forbid and methods & forbid:
		ok = False
		parts.append(f"avoid: {', '.join(sorted(methods & forbid))}")
	is_fragile = bool(spec.get("fragile", False))
	passed = True if is_fragile else ok
	issues_flag = (not ok) if is_fragile else False
	return _base_result(
		spec,
		passed=passed,
		issues=issues_flag,
		message="Approach looks good." if ok else "Approach check: " + "; ".join(parts) + ".",
		next_action=spec.get("next_action") or ("; ".join(parts).capitalize() + "." if parts else ""),
		details={"methods": sorted(methods)},
	)



def _grade_callable(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	if spec.get("callable") == "__assertion__" or (
		spec.get("expression") and not spec.get("callable")
	):
		return _grade_assertion_expression(spec, namespace)

	fn_name = spec.get("callable") or spec.get("name")
	fn = namespace.get(fn_name) if fn_name else None
	if not callable(fn):
		return _base_result(
			spec,
			passed=False,
			message=f"Grader `{fn_name}` is unavailable.",
			next_action="Contact an instructor — this exercise grader is misconfigured.",
		)

	args_spec = spec.get("args")
	try:
		if isinstance(args_spec, list):
			ok = bool(fn(*[namespace.get(name) for name in args_spec]))
		elif isinstance(args_spec, dict):
			kwargs: dict[str, Any] = {}
			for key, ref in args_spec.items():
				if isinstance(ref, str) and ref in namespace:
					kwargs[key] = namespace[ref]
				elif isinstance(ref, str) and ("." in ref or "[" in ref):
					kwargs[key] = _resolve_path(namespace, ref)
				else:
					kwargs[key] = ref
			ok = bool(fn(**kwargs))
		else:
			ok = bool(fn())
	except Exception as exc:
		return _base_result(
			spec,
			passed=False,
			message=f"Grader error: {exc}",
			next_action=spec.get("next_action") or "Fix runtime issues, then re-evaluate.",
		)
	return _base_result(
		spec,
		passed=ok,
		message=spec.get("success_message")
		or ("Check passed." if ok else (spec.get("failure_message") or "Check did not pass yet.")),
		next_action="" if ok else (spec.get("next_action") or "Re-read the prompt and adjust your approach."),
	)


def _grade_assertion_expression(spec: dict[str, Any], namespace: dict[str, Any], **_kwargs) -> dict[str, Any]:
	expression = spec.get("expression") or ""
	try:
		ok = bool(eval(expression, namespace, namespace))  # noqa: S307 — exercise sandbox namespace
		error = None
	except Exception as exc:
		ok = False
		error = str(exc)
	return _base_result(
		spec,
		passed=ok,
		message=("Assertion passed." if ok else (error or spec.get("failure_message") or "Assertion failed.")),
		next_action="" if ok else (spec.get("next_action") or "Adjust your solution and try Evaluate again."),
	)


def _grade_any_of(spec: dict[str, Any], namespace: dict[str, Any], **kwargs) -> dict[str, Any]:
	strategies = spec.get("strategies") or []
	matched = None
	child_results = []
	for strategy in strategies:
		strategy_id = strategy.get("id") or strategy.get("name") or "strategy"
		nested = strategy.get("graders") or []
		results = [run_grader(g, namespace, **kwargs) for g in nested]
		child_results.append({"id": strategy_id, "results": results})
		if results and all(r.get("passed") for r in results):
			matched = strategy_id
			break
	ok = matched is not None
	return _base_result(
		spec,
		passed=ok,
		message=f"Matched strategy `{matched}`." if ok else "No accepted strategy matched yet.",
		next_action=spec.get("next_action") or "Try one of the accepted solution approaches for this task.",
		details={"strategies": child_results, "matched_strategy": matched},
	)


def _grade_soft_skill(spec: dict[str, Any], namespace: dict[str, Any], **kwargs) -> dict[str, Any]:
	"""Score reflection like the plotting bonus: optional credit, never a core failure."""
	response = kwargs.get("soft_skill_response") or namespace.get("soft_skill_response") or ""
	text = str(response).strip()
	min_chars = int(spec.get("min_chars", 40))
	min_words = int(spec.get("min_words", 8))
	words = [w for w in re.split(r"\s+", text) if w]
	attempted = bool(text)
	ok = len(text) >= min_chars and len(words) >= min_words
	if ok:
		message = "Reflection complete."
	elif not attempted:
		message = "Reflection incomplete: write a short response for credit."
	else:
		message = (
			f"Reflection incomplete: need at least {min_words} words "
			f"(≥{min_chars} characters); found {len(words)}."
		)
	return _base_result(
		spec,
		passed=ok,
		message=message,
		next_action=spec.get("next_action")
		or f"Write a short reflection (≥{min_words} words) in the Reflection section.",
		details={"chars": len(text), "words": len(words), "attempted": attempted},
	)


GRADER_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
	"required_variable": _grade_required_variable,
	"equals": _grade_equals,
	"frame_equal": _grade_frame_equal,
	"series_close": _grade_series_close,
	"set_equal": _grade_set_equal,
	"contains_columns": _grade_contains_columns,
	"shape": _grade_shape,
	"dtype": _grade_dtype,
	"invariant": _grade_invariant,
	"ast_process": _grade_ast_process,
	"callable": _grade_callable,
	"any_of": _grade_any_of,
	"accepted_strategies": _grade_any_of,
	"soft_skill": _grade_soft_skill,
	"expected_value": _grade_equals,
	"assertion": _grade_assertion_expression,
}


def run_grader(spec: dict[str, Any], namespace: dict[str, Any], **kwargs) -> dict[str, Any]:
	handler = GRADER_HANDLERS.get(str(spec.get("type") or ""))
	if handler is None:
		return _base_result(
			spec,
			passed=False,
			message=f"Unknown grader type `{spec.get('type')}`.",
			next_action="Update the exercise grader configuration.",
		)
	when = spec.get("when_difficulty")
	if when:
		data = namespace.get("data") if isinstance(namespace.get("data"), dict) else {}
		difficulty = str(data.get("selected_feature") or data.get("difficulty") or "easy").lower()
		if difficulty not in {str(x).lower() for x in _as_list(when)}:
			return _base_result(
				spec,
				passed=True,
				message="Skipped for this difficulty.",
				details={"skipped": True},
			)
	return handler(spec, namespace, **kwargs)


def legacy_rules_to_graders(evaluation_rules: dict[str, Any]) -> list[dict[str, Any]]:
	"""Convert v1 required_variables / expected_values / assertions into typed graders."""
	graders: list[dict[str, Any]] = []
	for name in evaluation_rules.get("required_variables") or []:
		graders.append(
			{
				"id": f"required_{name}",
				"type": "required_variable",
				"variable": name,
				"section": SECTION_CORE,
				"visibility": VISIBILITY_VISIBLE,
				"soft": True,
				"next_action": f"Define `{name}` in your notebook.",
			}
		)
	for name, expected in (evaluation_rules.get("expected_values") or {}).items():
		graders.append(
			{
				"id": f"equals_{name}",
				"type": "equals",
				"variable": name,
				"expected": expected,
				"section": SECTION_CORE,
				"visibility": VISIBILITY_VISIBLE,
				"soft": False,
				"next_action": f"Recompute `{name}` from the provided data.",
			}
		)
	for index, expression in enumerate(evaluation_rules.get("assertions") or []):
		graders.append(
			{
				"id": f"assertion_{index}",
				"type": "assertion",
				"callable": "__assertion__",
				"expression": expression,
				"section": SECTION_CORE,
				"visibility": VISIBILITY_VISIBLE,
				"soft": False,
				"next_action": "Re-read the prompt and adjust your solution.",
				"failure_message": evaluation_rules.get("failure_message") or "Assertion failed.",
				"success_message": "Assertion passed.",
			}
		)
	return graders


def normalize_evaluation_rules(evaluation_rules: dict[str, Any] | None) -> dict[str, Any]:
	rules = deepcopy(evaluation_rules or {})
	if rules.get("graders"):
		rules.setdefault("version", 2)
		return rules
	graders = legacy_rules_to_graders(rules)
	rules["version"] = 1
	rules["graders"] = graders
	rules.setdefault("second_seed_recheck", {"enabled": False, "seed_offset": 10007})
	rules.setdefault(
		"soft_skill",
		{"required_for_full_completion": False, "min_chars": 40, "min_words": 8},
	)
	return rules


def _section_bucket() -> dict[str, Any]:
	return {"passed": 0, "total": 0, "checks": []}


def build_rubric(checks: list[dict[str, Any]]) -> dict[str, Any]:
	rubric = {
		SECTION_CORE: _section_bucket(),
		SECTION_APPROACH: _section_bucket(),
		SECTION_BONUS: _section_bucket(),
		SECTION_REFLECTION: _section_bucket(),
	}
	for check in checks:
		section = check.get("section") or SECTION_CORE
		if section not in rubric:
			section = SECTION_CORE
		bucket = rubric[section]
		if check.get("details", {}).get("skipped"):
			continue
		bucket["total"] += 1
		if check.get("passed"):
			bucket["passed"] += 1
		bucket["checks"].append(check)
	return rubric


def determine_band(
	*,
	ran: bool,
	core_passed: bool,
	has_issues: bool,
	reflection_ok: bool | None = None,
	require_reflection: bool = False,
) -> str:
	"""Band from core + approach issues. Reflection / plotting bonus are optional credit."""
	_ = (reflection_ok, require_reflection)
	if not ran or not core_passed:
		return BAND_INCOMPLETE
	if has_issues:
		return BAND_PASS_WITH_ISSUES
	return BAND_PASS


def _values_close_enough(actual: Any, expected: Any) -> bool:
	"""Loose equality for feedback mismatch detection (mirrors student-facing tolerances)."""
	if isinstance(expected, pd.DataFrame) or isinstance(actual, pd.DataFrame):
		return frame_equal(actual, expected)
	return values_equal(actual, expected, atol=1e-3, rtol=1e-3, normalize_strings=False)


def collect_task_answer_items(namespace: dict[str, Any]) -> list[dict[str, Any]]:
	"""Compare student outputs to `task` expected values for feedback."""
	task = namespace.get("task")
	if not isinstance(task, dict):
		return []

	items: list[dict[str, Any]] = []
	expected = task.get("expected")
	expected_df = task.get("expected_df")
	mode = str(task.get("mode") or "")

	# Scalar summary answers (pandas intro easy).
	if mode == "summary" or (
		expected is not None
		and not isinstance(expected, dict)
		and (expected_df is None or (isinstance(expected_df, pd.DataFrame) and expected_df.empty))
	):
		actual = namespace.get("answer")
		if not _values_close_enough(actual, expected):
			items.append(
				{
					"label": "answer",
					"incorrect": display_value(actual),
					"correct": display_value(expected),
				}
			)
		return items

	# Dict of expected answers / frames (descriptive stats, A/B, transforms).
	if isinstance(expected, dict):
		answer_dict = namespace.get("answer") if isinstance(namespace.get("answer"), dict) else None
		for key, exp_val in expected.items():
			if isinstance(exp_val, pd.DataFrame):
				actual = namespace.get(key)
				if not _values_close_enough(actual, exp_val):
					diff = frame_diff(actual, exp_val) if isinstance(actual, pd.DataFrame) else {}
					items.append(
						{
							"label": str(key),
							"incorrect": diff.get("message") or display_value(actual),
							"correct": display_value(exp_val),
						}
					)
				continue
			if answer_dict is not None and key in answer_dict:
				actual = answer_dict.get(key)
			elif key in namespace:
				actual = namespace.get(key)
			else:
				actual = None if answer_dict is None else answer_dict.get(key)
			if not _values_close_enough(actual, exp_val):
				items.append(
					{
						"label": str(key),
						"incorrect": display_value(actual),
						"correct": display_value(exp_val),
					}
				)
		return items

	# Expected dataframe result (pandas intro subset / messy dataset).
	if isinstance(expected_df, pd.DataFrame) and len(expected_df) > 0:
		actual = namespace.get("df")
		if not _values_close_enough(actual, expected_df):
			diff = frame_diff(actual, expected_df) if isinstance(actual, pd.DataFrame) else {}
			items.append(
				{
					"label": "df",
					"incorrect": diff.get("message") or display_value(actual),
					"correct": display_value(expected_df),
				}
			)
		return items

	return items


def _strip_expected_from_details(details: dict[str, Any]) -> dict[str, Any]:
	cleaned = dict(details)
	cleaned.pop("expected", None)
	cleaned.pop("expected_display", None)
	for row in cleaned.get("preview") or []:
		if isinstance(row, dict):
			row.pop("expected", None)
			row["expected_hidden"] = True
	return cleaned


def _reveal_expected_in_details(details: dict[str, Any]) -> dict[str, Any]:
	revealed = dict(details)
	for row in revealed.get("preview") or []:
		if isinstance(row, dict):
			row["expected_hidden"] = False
	return revealed


def apply_answer_feedback(
	checks: list[dict[str, Any]],
	namespace: dict[str, Any],
	*,
	reveal_info: dict[str, Any],
) -> dict[str, Any]:
	"""Annotate failed checks with what was wrong and (optionally) the correct answer."""
	revealed = bool(reveal_info.get("revealed"))
	policy = reveal_info.get("policy") or ANSWER_POLICY_HIDE
	task_items = collect_task_answer_items(namespace)

	for check in checks:
		if check.get("passed") or check.get("details", {}).get("skipped"):
			continue
		details = check.get("details") if isinstance(check.get("details"), dict) else {}
		expected_display = details.get("expected_display")
		actual_display = details.get("actual_display")
		if actual_display and "got " not in (check.get("message") or ""):
			check["message"] = f"{check.get('message') or 'Incorrect.'} (got {actual_display})"
		if revealed and expected_display:
			check["correct_answer"] = expected_display
		elif policy == ANSWER_POLICY_OFFER and expected_display:
			check["can_reveal_answer"] = True
		if revealed:
			check["details"] = _reveal_expected_in_details(details)
		else:
			check["details"] = _strip_expected_from_details(details)

	# Assertion / callable failures often lack structured expected fields — use task.
	if task_items:
		incorrect_summary = "; ".join(
			f"`{item['label']}` was {item['incorrect']}" for item in task_items[:6]
		)
		correct_summary = "; ".join(
			f"`{item['label']}` → {item['correct']}" for item in task_items[:6]
		)
		for check in checks:
			if check.get("passed") or check.get("details", {}).get("skipped"):
				continue
			if check.get("section") not in {SECTION_CORE, None, ""}:
				continue
			if check.get("type") in {"assertion", "callable", "any_of", "accepted_strategies"} or not check.get(
				"correct_answer"
			):
				# Prefer concrete mismatch text over a generic assertion failure.
				if check.get("type") in {"assertion", "callable"} or "match" in (check.get("message") or "").lower():
					check["message"] = f"Incorrect: {incorrect_summary}."
				if revealed:
					check["correct_answer"] = correct_summary
					check.pop("can_reveal_answer", None)
				elif policy == ANSWER_POLICY_OFFER:
					check["can_reveal_answer"] = True

	can_reveal = any(bool(c.get("can_reveal_answer")) for c in checks)
	return {
		"policy": policy,
		"revealed": revealed,
		"can_reveal": can_reveal,
		"items": (
			[
				{
					"label": item["label"],
					"incorrect": item["incorrect"],
					**({"correct": item["correct"]} if revealed else {}),
				}
				for item in task_items
			]
			if task_items
			else []
		),
	}


def evaluate_with_graders(
	namespace: dict[str, Any],
	evaluation_rules: dict[str, Any] | None,
	*,
	mode: str = MODE_EVALUATE,
	cell_sources: list[str] | None = None,
	soft_skill_response: str | None = None,
	soft_skill_prompt: str | None = None,
	plotting_bonus: dict[str, Any] | None = None,
	reveal_expected: bool = False,
	second_seed_ok: bool | None = None,
) -> dict[str, Any]:
	"""Run typed graders and assemble rubric + band."""
	rules = normalize_evaluation_rules(evaluation_rules)
	mode = MODE_RUN if mode == MODE_RUN else MODE_EVALUATE
	checks: list[dict[str, Any]] = []
	difficulty = difficulty_from_namespace(namespace)
	reveal_info = resolve_answer_reveal(difficulty, reveal_requested=reveal_expected)

	for spec in rules.get("graders") or []:
		visibility = spec.get("visibility") or VISIBILITY_VISIBLE
		is_soft = bool(spec.get("soft", spec.get("type") in {"required_variable", "contains_columns", "shape", "ast_process"}))
		if mode == MODE_RUN and not is_soft:
			continue
		if mode == MODE_RUN and visibility == VISIBILITY_HIDDEN:
			continue
		result = run_grader(
			spec,
			namespace,
			cell_sources=cell_sources or [],
			soft_skill_response=soft_skill_response,
		)
		checks.append(result)

	# Soft-skill reflection — optional credit (same spirit as plotting bonus).
	soft_cfg = rules.get("soft_skill") or {}
	prompt = soft_skill_prompt or ""
	if not prompt and isinstance(namespace.get("data"), dict):
		prompt = str(namespace["data"].get("soft_skill_prompt") or "")
	reflection_ok = None
	if mode == MODE_EVALUATE and prompt.strip():
		soft_result = run_grader(
			{
				"id": "soft_skill",
				"type": "soft_skill",
				"section": SECTION_REFLECTION,
				"visibility": VISIBILITY_VISIBLE,
				**soft_cfg,
			},
			namespace,
			soft_skill_response=soft_skill_response or "",
		)
		checks.append(soft_result)
		reflection_ok = bool(soft_result.get("passed"))

	# Plotting bonus as rubric bonus section
	if plotting_bonus is not None:
		checks.append(
			{
				"id": "plotting_bonus",
				"type": "plotting_bonus",
				"section": SECTION_BONUS,
				"visibility": VISIBILITY_VISIBLE,
				"passed": bool(plotting_bonus.get("passed")),
				"issues": False,
				"message": plotting_bonus.get("message") or "Plotting bonus.",
				"next_action": ""
				if plotting_bonus.get("passed")
				else "Create the requested plot (and style mods on medium/hard) for bonus credit.",
				"hint": "",
				"details": plotting_bonus,
			}
		)

	# Second-seed fragility
	if mode == MODE_EVALUATE and second_seed_ok is False:
		checks.append(
			{
				"id": "second_seed_recheck",
				"type": "second_seed_recheck",
				"section": SECTION_APPROACH,
				"visibility": VISIBILITY_VISIBLE,
				"passed": True,
				"issues": True,
				"message": "Solution works for this seed but failed a second seeded scenario.",
				"next_action": "Avoid hard-coded numbers — derive answers from `df` / `task`.",
				"hint": "Your logic should generalize across seeds.",
				"details": {},
			}
		)

	answer_feedback = apply_answer_feedback(checks, namespace, reveal_info=reveal_info)

	rubric = build_rubric(checks)
	core = rubric[SECTION_CORE]
	core_passed = core["total"] == 0 or core["passed"] == core["total"]
	# Optional sections (reflection / plotting bonus) never create approach "issues".
	has_issues = any(
		c.get("issues")
		for c in checks
		if c.get("section") not in {SECTION_REFLECTION, SECTION_BONUS}
		and c.get("type") not in {"soft_skill", "plotting_bonus"}
	) or (second_seed_ok is False)
	bonus_passed = bool(plotting_bonus and plotting_bonus.get("passed"))
	band = determine_band(
		ran=True,
		core_passed=core_passed,
		has_issues=has_issues,
		reflection_ok=reflection_ok,
		require_reflection=False,
	)

	failed = [
		c
		for c in checks
		if not c.get("passed")
		and not c.get("details", {}).get("skipped")
		and c.get("section") not in {SECTION_REFLECTION, SECTION_BONUS}
		and c.get("type") not in {"soft_skill", "plotting_bonus"}
	]
	if mode == MODE_RUN:
		if not failed:
			summary = "Looks promising — run Evaluate Exercise when you want credit."
		else:
			first = failed[0]
			summary = first.get("message") or first.get("next_action") or "Keep going."
		soft_messages = [c.get("message") for c in failed if c.get("message")]
		correct_answers = [c.get("correct_answer") for c in failed if c.get("correct_answer")]
		return {
			"mode": mode,
			"passed": False,
			"core_passed": False,
			"band": BAND_INCOMPLETE,
			"summary": summary,
			"checks": [c for c in checks if c.get("visibility") != VISIBILITY_HIDDEN],
			"rubric": rubric,
			"soft_feedback": {
				"status": "close" if not failed else "needs_work",
				"messages": soft_messages or [c.get("message") for c in checks],
				"next_actions": [c.get("next_action") for c in failed if c.get("next_action")],
				"correct_answers": correct_answers,
				"can_reveal_answer": bool(answer_feedback.get("can_reveal")),
			},
			"plotting_bonus": plotting_bonus,
			"reveal_expected": bool(answer_feedback.get("revealed")),
			"answer_feedback": answer_feedback,
		}

	if core_passed and not has_issues:
		summary = rules.get("success_message") or "Exercise checks complete."
	elif core_passed and has_issues:
		summary = "Core checks passed with issues — see Approach."
	else:
		first = next((c for c in checks if c.get("section") == SECTION_CORE and not c.get("passed")), None)
		# Prefer describing what was incorrect over a generic next-action prompt.
		summary = (
			(first.get("message") if first else None)
			or (first.get("next_action") if first else None)
			or rules.get("failure_message")
			or "Review the notebook and try again."
		)

	visible_checks = list(checks)
	for check in visible_checks:
		if check.get("visibility") == VISIBILITY_HIDDEN and not check.get("passed"):
			check["message"] = "A hidden integrity check did not pass yet."
			check["next_action"] = check.get("next_action") or "Generalize your solution — avoid hard-coding."
			check.pop("correct_answer", None)
			check.pop("can_reveal_answer", None)

	return {
		"mode": mode,
		"passed": bool(core_passed),
		"core_passed": bool(core_passed),
		"band": band,
		"summary": summary,
		"checks": visible_checks,
		"rubric": rubric,
		"soft_feedback": None,
		"plotting_bonus": plotting_bonus,
		"bonus_passed": bonus_passed,
		"matched_strategy": next(
			(
				c.get("details", {}).get("matched_strategy")
				for c in checks
				if c.get("type") in {"any_of", "accepted_strategies"} and c.get("passed")
			),
			None,
		),
		"second_seed_ok": second_seed_ok,
		"reveal_expected": bool(answer_feedback.get("revealed")),
		"answer_feedback": answer_feedback,
		"success_message": rules.get("success_message"),
		"failure_message": rules.get("failure_message"),
	}


def soft_skill_config(evaluation_rules: dict[str, Any] | None) -> dict[str, Any]:
	rules = normalize_evaluation_rules(evaluation_rules)
	return dict(rules.get("soft_skill") or {})


def second_seed_config(evaluation_rules: dict[str, Any] | None) -> dict[str, Any]:
	rules = normalize_evaluation_rules(evaluation_rules)
	cfg = rules.get("second_seed_recheck")
	if cfg is False:
		return {"enabled": False, "seed_offset": 10007}
	if cfg is True or cfg is None:
		return {"enabled": True, "seed_offset": 10007}
	if isinstance(cfg, dict):
		return {"enabled": bool(cfg.get("enabled", True)), "seed_offset": int(cfg.get("seed_offset", 10007))}
	return {"enabled": False, "seed_offset": 10007}
