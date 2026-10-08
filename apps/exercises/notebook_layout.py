"""Build the default exercise notebook layout (work cells + plotting bonus)."""

from __future__ import annotations

from typing import Any

# Preferred aliases for whole-package imports preloaded into the sandbox.
# Selective libraries (sklearn, xgboost, …) are also preloaded under their package name.
# Matplotlib is reserved for the plotting-bonus code cell but is still preloaded.
AUTO_IMPORT_LINES: dict[str, str] = {
	"numpy": "import numpy as np",
	"pandas": "import pandas as pd",
	"seaborn": "import seaborn as sns",
}

IMPORT_ALIASES: dict[str, str] = {
	"numpy": "np",
	"pandas": "pd",
	"matplotlib.pyplot": "plt",
	"seaborn": "sns",
}

SELECTIVE_IMPORT_ROOTS = frozenset({"sklearn", "xgboost", "lightgbm", "catboost"})


def auto_import_source(allowed_imports: list[str] | None) -> str:
	"""Return the import statements that used to appear in the locked imports cell.

	Kept for tests/helpers; the notebook UI no longer shows an imports cell.
	Libraries are preloaded in the sandbox namespace instead.
	"""
	lines: list[str] = []
	seen: set[str] = set()
	for name in allowed_imports or []:
		key = str(name or "").strip()
		if not key or key in seen:
			continue
		seen.add(key)
		root = key.split(".", 1)[0]
		if root in SELECTIVE_IMPORT_ROOTS:
			continue
		if key == "matplotlib.pyplot" or root == "matplotlib":
			continue
		line = AUTO_IMPORT_LINES.get(key)
		if line:
			lines.append(line)
			continue
		# Skip dotted modules we don't have an explicit line for.
		if "." in key:
			continue
		lines.append(f"import {key}")
	return ("\n".join(lines) + "\n") if lines else "# Libraries for this exercise are preloaded.\n"


def describe_preloaded_libraries(allowed_imports: list[str] | None) -> list[str]:
	"""Return markdown labels for libraries preloaded into the exercise sandbox."""
	labels: list[str] = []
	seen: set[str] = set()
	for name in allowed_imports or []:
		key = str(name or "").strip()
		if not key or key in seen:
			continue
		seen.add(key)
		alias = IMPORT_ALIASES.get(key)
		if alias:
			labels.append(f"`{key}` as `{alias}`")
		else:
			labels.append(f"`{key}`")
	return labels


def format_preloaded_libraries_note(allowed_imports: list[str] | None) -> str:
	"""Sentence listing preloaded libraries for the difficulty/task prompt."""
	labels = describe_preloaded_libraries(allowed_imports)
	if not labels:
		return ""
	return (
		"Preloaded libraries (already imported — use them directly): "
		+ ", ".join(labels)
		+ "."
	)


def with_preloaded_libraries_note(prompt: str | None, allowed_imports: list[str] | None) -> str:
	"""Append the preloaded-libraries note to a task prompt when libraries exist."""
	base = (prompt or "").strip()
	note = format_preloaded_libraries_note(allowed_imports)
	if not note:
		return base
	if not base:
		return note
	if note in base:
		return base
	return f"{base}\n\n{note}"


def without_imports_cells(cells: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
	"""Drop legacy locked imports cells from a notebook state."""
	return [
		dict(cell)
		for cell in (cells or [])
		if str((cell or {}).get("role") or "") != "imports"
	]


def plotting_bonus_code_source() -> str:
	return "import matplotlib.pyplot as plt\n"


def build_starter_notebook(
	allowed_imports: list[str] | None,
	*,
	plotting_bonus_prompt: str = "",
	work_cell_count: int = 2,
) -> list[dict[str, Any]]:
	"""Return the default notebook: work cells and optional plotting bonus.

	Allowed libraries are preloaded in the sandbox (not shown as a notebook cell).
	"""
	cells: list[dict[str, Any]] = []
	for _ in range(max(1, int(work_cell_count))):
		cells.append({"source": "", "cell_type": "code", "locked": False, "role": "work"})

	imports = {str(item).strip() for item in (allowed_imports or []) if str(item).strip()}
	has_matplotlib = "matplotlib.pyplot" in imports or "matplotlib" in imports
	if has_matplotlib:
		prompt = (plotting_bonus_prompt or "").strip() or "### Plotting bonus"
		cells.append(
			{
				"source": prompt,
				"cell_type": "markdown",
				"locked": True,
				"role": "plotting_bonus_prompt",
			}
		)
		cells.append(
			{
				"source": plotting_bonus_code_source(),
				"cell_type": "code",
				"locked": False,
				"role": "plotting_bonus",
			}
		)
	return cells


def sync_plotting_bonus_prompt(cells: list[dict[str, Any]] | None, prompt: str) -> list[dict[str, Any]]:
	"""Update the locked plotting-bonus markdown cell source when the scenario changes."""
	updated = [dict(cell) for cell in (cells or [])]
	text = (prompt or "").strip()
	if not text:
		return updated
	for cell in updated:
		if cell.get("role") == "plotting_bonus_prompt" or (
			cell.get("cell_type") == "markdown" and cell.get("locked")
		):
			cell["source"] = text
			cell["cell_type"] = "markdown"
			cell["locked"] = True
			cell["role"] = "plotting_bonus_prompt"
			break
	return updated
