"""Plotting bonus: task generation, AST inspection, and credit rules."""

from __future__ import annotations

import ast
import re
from typing import Any

SOURCE_PLOT_KIND: dict[str, str] = {
	"pandas_intro": "any",
	"data_transformation": "bar",
	"messy_dataset": "histogram",
	"data_quality": "missingness_bar",
	"missing_values": "missingness_bar",
	"descriptive_statistics": "box",
	"ab_testing": "ab_choice",  # resolved with seed to hist_overlap or violin
}

KIND_LABELS: dict[str, str] = {
	"any": "any matplotlib plot",
	"bar": "a bar chart (`plt.bar` / `plt.barh`)",
	"histogram": "a histogram (`plt.hist`)",
	"missingness_bar": "a missingness bar chart (null counts with `plt.bar` / `plt.barh`)",
	"box": "a box plot (`plt.boxplot`)",
	"hist_overlap": "overlapping histograms for the two groups (`plt.hist` twice, ideally with `alpha`)",
	"violin": "a violin plot (`plt.violinplot`)",
}

PLOT_METHODS: dict[str, set[str]] = {
	"any": {
		"plot",
		"scatter",
		"bar",
		"barh",
		"hist",
		"boxplot",
		"violinplot",
		"pie",
		"imshow",
		"contour",
		"hexbin",
		"stem",
		"fill_between",
		"histplot",
		"barplot",
		"countplot",
		"kdeplot",
		"lineplot",
		"heatmap",
	},
	"bar": {"bar", "barh", "barplot", "countplot"},
	"histogram": {"hist", "histplot"},
	"missingness_bar": {"bar", "barh", "barplot"},
	"box": {"boxplot"},
	"hist_overlap": {"hist", "histplot"},
	"violin": {"violinplot"},
}

COLOR_KW = {"color", "c", "facecolor", "edgecolor", "cmap", "colors", "fc", "ec"}
MARKER_KW = {"marker", "markersize", "ms", "markerfacecolor", "markeredgecolor", "mfc", "mec"}
FONT_KW = {
	"fontsize",
	"fontfamily",
	"fontweight",
	"fontstyle",
	"fontdict",
	"family",
	"weight",
	"labelsize",
	"labelfontfamily",
}
MISSINGNESS_RE = re.compile(
	r"\b(isna|isnull|notna|notnull)\s*\(|\.isna\s*\(|\.isnull\s*\(|isna\s*\(|isnull\s*\(",
	re.IGNORECASE,
)


def _difficulty(value: Any) -> str:
	text = str(value or "easy").strip().lower()
	return text if text in {"easy", "medium", "hard"} else "easy"


def _modifications_required(difficulty: str) -> int:
	if difficulty == "hard":
		return 2
	if difficulty == "medium":
		return 1
	return 0


def resolve_plot_kind(source: str, seed: int = 42) -> str:
	base = SOURCE_PLOT_KIND.get(source, "any")
	if base != "ab_choice":
		return base
	return "hist_overlap" if int(seed) % 2 == 0 else "violin"


def build_plotting_bonus(
	source: str,
	*,
	difficulty: str = "easy",
	seed: int = 42,
) -> dict[str, Any]:
	"""Return the plotting-bonus specification attached to each exercise task."""
	level = _difficulty(difficulty)
	kind = resolve_plot_kind(source, seed=seed)
	required_mods = _modifications_required(level)
	label = KIND_LABELS.get(kind, "a plot")
	if required_mods <= 0:
		mod_text = "No style modifications are required on easy — creating the plot is enough."
	elif required_mods == 1:
		mod_text = (
			"For credit on medium, customize the plot with **at least one** style change "
			"(color, marker, or font size/family)."
		)
	else:
		mod_text = (
			"For credit on hard, customize the plot with **at least two** different style changes "
			"(from color, marker, and font)."
		)
	prompt = (
		"### Plotting bonus\n"
		f"Create {label}. {mod_text}\n"
		"This is optional for passing the main exercise, but successful bonus plots earn badge progress."
	)
	return {
		"enabled": True,
		"kind": kind,
		"kind_label": label,
		"modifications_required": required_mods,
		"difficulty": level,
		"prompt": prompt,
	}


def format_plotting_bonus_prompt(bonus: dict[str, Any] | None) -> str:
	if not bonus or not bonus.get("enabled"):
		return ""
	return str(bonus.get("prompt") or "").strip()


def _call_name(node: ast.AST) -> str | None:
	if isinstance(node, ast.Name):
		return node.id
	if isinstance(node, ast.Attribute):
		return node.attr
	return None


def _keyword_names(call: ast.Call) -> set[str]:
	names: set[str] = set()
	for keyword in call.keywords:
		if keyword.arg:
			names.add(keyword.arg)
	return names


def analyze_notebook_plotting(cell_sources: list[str]) -> dict[str, Any]:
	"""Inspect student cell sources for plot types and style customizations."""
	joined = "\n".join(cell_sources or [])
	methods: set[str] = set()
	hist_calls = 0
	color_hits = marker_hits = font_hits = 0
	has_alpha_hist = False

	for source in cell_sources or []:
		try:
			tree = ast.parse(source or "")
		except SyntaxError:
			continue
		for node in ast.walk(tree):
			if not isinstance(node, ast.Call):
				continue
			name = _call_name(node.func)
			if not name:
				continue
			methods.add(name)
			kwargs = _keyword_names(node)
			if name in {"hist", "histplot"}:
				hist_calls += 1
				if "alpha" in kwargs:
					has_alpha_hist = True
			if kwargs & COLOR_KW:
				color_hits += 1
			if kwargs & MARKER_KW:
				marker_hits += 1
			if kwargs & FONT_KW or (name in {"title", "xlabel", "ylabel", "suptitle", "set_title", "set_xlabel", "set_ylabel"} and kwargs & FONT_KW):
				font_hits += 1
			# Common font APIs: ax.set_xlabel('...', fontsize=12)
			if name in {"title", "xlabel", "ylabel", "suptitle", "set_title", "set_xlabel", "set_ylabel", "tick_params"}:
				if kwargs & ({"fontsize", "labelsize", "size"} | FONT_KW):
					font_hits += 1
			# plt.rc / rcParams font updates
			if name in {"rc", "rc_context"} and any("font" in (k or "") for k in kwargs):
				font_hits += 1

	# String fallback for rcParams['font.size'] = ...
	if re.search(r"rcParams\s*\[.*?font", joined, re.IGNORECASE):
		font_hits += 1
	if re.search(r"\b(set_fontsize|tick_params\s*\(.*labelsize)", joined, re.IGNORECASE):
		font_hits += 1

	mod_categories = []
	if color_hits:
		mod_categories.append("color")
	if marker_hits:
		mod_categories.append("marker")
	if font_hits:
		mod_categories.append("font")

	return {
		"methods": sorted(methods),
		"hist_calls": hist_calls,
		"has_alpha_hist": has_alpha_hist,
		"has_missingness_signal": bool(MISSINGNESS_RE.search(joined)),
		"modification_categories": mod_categories,
		"modifications_count": len(mod_categories),
	}


def _kind_matched(kind: str, analysis: dict[str, Any], figure_count: int) -> bool:
	methods = set(analysis.get("methods") or [])
	if kind == "any":
		wanted = PLOT_METHODS["any"]
		return bool(methods & wanted) or figure_count > 0
	if kind == "hist_overlap":
		hist_ok = analysis.get("hist_calls", 0) >= 2 or (
			analysis.get("hist_calls", 0) >= 1 and analysis.get("has_alpha_hist")
		)
		return hist_ok and bool(methods & PLOT_METHODS["hist_overlap"])
	if kind == "missingness_bar":
		return bool(methods & PLOT_METHODS["missingness_bar"]) and bool(analysis.get("has_missingness_signal"))
	wanted = PLOT_METHODS.get(kind, set())
	return bool(methods & wanted)


def evaluate_plotting_bonus(
	*,
	bonus: dict[str, Any] | None,
	cell_sources: list[str],
	figure_count: int = 0,
) -> dict[str, Any]:
	"""Score the plotting bonus without affecting the main exercise pass/fail."""
	if not bonus or not bonus.get("enabled"):
		return {
			"attempted": False,
			"passed": False,
			"kind_matched": False,
			"plots_created": 0,
			"modifications_count": 0,
			"modification_categories": [],
			"modifications_required": 0,
			"message": "No plotting bonus for this exercise.",
		}

	kind = str(bonus.get("kind") or "any")
	required_mods = int(bonus.get("modifications_required") or 0)
	analysis = analyze_notebook_plotting(cell_sources)
	kind_matched = _kind_matched(kind, analysis, figure_count)
	mods = int(analysis.get("modifications_count") or 0)
	categories = list(analysis.get("modification_categories") or [])
	plots_created = 1 if kind_matched or figure_count > 0 and kind == "any" else (1 if kind_matched else 0)
	if kind_matched:
		plots_created = max(plots_created, 1)
		if figure_count > 0:
			plots_created = max(plots_created, 1)

	passed = bool(kind_matched and mods >= required_mods)
	if not kind_matched:
		message = f"Plotting bonus incomplete: still need {KIND_LABELS.get(kind, kind)}."
	elif mods < required_mods:
		message = (
			f"Plot type looks good, but need {required_mods} style customization"
			f"{'s' if required_mods != 1 else ''} "
			f"(color / marker / font); found {mods}."
		)
	else:
		message = (
			f"Plotting bonus earned ({KIND_LABELS.get(kind, kind)}"
			+ (f", style: {', '.join(categories)}" if categories else "")
			+ ")."
		)

	return {
		"attempted": bool(kind_matched or figure_count > 0 or mods > 0),
		"passed": passed,
		"kind": kind,
		"kind_matched": kind_matched,
		"plots_created": 1 if kind_matched else 0,
		"modifications_count": mods if kind_matched else 0,
		"modification_categories": categories if kind_matched else [],
		"modifications_required": required_mods,
		"message": message,
	}


def attach_plotting_bonus_to_prepared(
	prepared: dict[str, Any],
	*,
	source: str,
	difficulty: str,
	seed: int,
) -> dict[str, Any]:
	"""Mutate prepared namespace context to include plotting bonus on ``task``."""
	if not source:
		return prepared
	bonus = build_plotting_bonus(source, difficulty=difficulty, seed=seed)
	task = prepared.get("task")
	if not isinstance(task, dict):
		task = {"prompt": ""}
		prepared["task"] = task
	task["plotting_bonus"] = bonus
	bonus_prompt = format_plotting_bonus_prompt(bonus)
	base_prompt = str(task.get("prompt") or "").strip()
	if bonus_prompt:
		task["prompt"] = f"{base_prompt}\n\n{bonus_prompt}".strip() if base_prompt else bonus_prompt
	return prepared
