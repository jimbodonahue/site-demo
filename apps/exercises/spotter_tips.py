"""Spotter snippets: short, non-spoilery tool reminders per exercise difficulty.

Medium/hard intentionally omit earlier-level tips. Snippets use placeholders
like ``df['column']`` so they are not paste-ready solutions.

Edit ``apps/exercises/content/spotter_tips.json`` to update the copy.
"""

from __future__ import annotations

from typing import Any

from apps.exercises.content import load_json


def _tips_bundle() -> dict[str, dict[str, list[str]]]:
	raw = load_json("spotter_tips.json", default={})
	return raw if isinstance(raw, dict) else {}


def __getattr__(name: str):
	# Backward-compatible alias for tests/callers that imported SPOTTER_TIPS.
	if name == "SPOTTER_TIPS":
		return _tips_bundle()
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_spotter_tips(
	dataframe_source: str | None,
	difficulty: str | None = None,
) -> dict[str, list[str]] | list[str]:
	"""Return all difficulty tips for a source, or one difficulty's list."""
	source = (dataframe_source or "").strip()
	by_level = _tips_bundle().get(source) or {}
	if difficulty is None:
		return {
			"easy": list(by_level.get("easy") or []),
			"medium": list(by_level.get("medium") or []),
			"hard": list(by_level.get("hard") or []),
		}
	key = (difficulty or "easy").lower().strip()
	if key not in {"easy", "medium", "hard"}:
		key = "easy"
	return list(by_level.get(key) or [])


def spotter_tips_for_data_state(data_state: dict[str, Any] | None) -> list[str]:
	"""Resolve tips for the current exercise data_state."""
	state = data_state or {}
	source = state.get("dataframe_source") or ""
	difficulty = state.get("selected_feature") or state.get("difficulty") or "easy"
	tips = get_spotter_tips(source, difficulty)
	return tips if isinstance(tips, list) else []
