"""Load and render exercise copy / prompt templates from content files."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from string import Formatter
from typing import Any

CONTENT_ROOT = Path(__file__).resolve().parent
EXERCISES_ROOT = CONTENT_ROOT / "exercises"
PROMPTS_ROOT = CONTENT_ROOT / "prompts"


class _SafeFormatMap(dict):
	"""Leave unknown ``{placeholders}`` intact so partial templates still work."""

	def __missing__(self, key: str) -> str:
		return "{" + key + "}"


def exercise_dir(slug: str) -> Path:
	return EXERCISES_ROOT / slug


def load_text(relative: str | Path, default: str = "") -> str:
	path = CONTENT_ROOT / relative if not isinstance(relative, Path) else relative
	if not path.is_file():
		return default
	return path.read_text(encoding="utf-8").strip()


def load_json(relative: str | Path, default: Any = None) -> Any:
	path = CONTENT_ROOT / relative if not isinstance(relative, Path) else relative
	if not path.is_file():
		return {} if default is None else default
	return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def _cached_prompt_bundle(module: str) -> dict[str, Any]:
	return load_json(PROMPTS_ROOT / f"{module}.json", default={})


def load_prompt(module: str, template_key: str, default: str = "") -> str:
	"""Return a prompt template string from ``content/prompts/<module>.json``."""
	bundle = _cached_prompt_bundle(module)
	value = bundle.get(template_key, default)
	if value is None:
		return default
	return str(value)


def render_prompt(module: str, template_key: str, default: str = "", **kwargs: Any) -> str:
	"""Load a template and interpolate with ``str.format_map`` (safe for extras)."""
	template = load_prompt(module, template_key, default=default)
	if not template:
		return default
	# Convert non-strings conservatively for format fields.
	mapping = _SafeFormatMap({k: kwargs[k] for k in kwargs})
	try:
		return Formatter().vformat(template, (), mapping)
	except Exception:
		try:
			return template.format_map(mapping)
		except Exception:
			return template


def get_intro(slug: str) -> str:
	return load_text(exercise_dir(slug) / "intro.md")


def get_soft_skill(slug: str) -> str:
	return load_text(exercise_dir(slug) / "soft_skill.md")


def get_graphic_markup(slug: str) -> str:
	return load_text(exercise_dir(slug) / "graphic_markup.html")


def get_starter_code(slug: str) -> str:
	path = exercise_dir(slug) / "starter.py"
	if not path.is_file():
		return ""
	# Preserve trailing newline conventions for starter notebooks.
	return path.read_text(encoding="utf-8")


def get_messages(slug: str) -> dict[str, Any]:
	return load_json(exercise_dir(slug) / "messages.json", default={})


def apply_messages_to_rules(slug: str, evaluation_rules: dict[str, Any] | None) -> dict[str, Any]:
	"""Overlay success/failure/grader copy from content files onto evaluation_rules."""
	rules = dict(evaluation_rules or {})
	messages = get_messages(slug)
	if not messages:
		return rules
	if messages.get("success_message"):
		rules["success_message"] = messages["success_message"]
	if messages.get("failure_message"):
		rules["failure_message"] = messages["failure_message"]
	grader_msgs = {
		item.get("id"): item
		for item in (messages.get("graders") or [])
		if isinstance(item, dict) and item.get("id")
	}
	if grader_msgs and isinstance(rules.get("graders"), list):
		updated = []
		for grader in rules["graders"]:
			entry = dict(grader)
			overlay = grader_msgs.get(entry.get("id")) or {}
			for field in ("next_action", "failure_message", "success_message", "hint"):
				if overlay.get(field):
					entry[field] = overlay[field]
			updated.append(entry)
		rules["graders"] = updated
	return rules


def sync_exercise_from_content(exercise: Any) -> list[str]:
	"""Copy content-file fields onto an Exercise instance. Returns updated field names."""
	slug = getattr(exercise, "slug", "") or ""
	if not slug or not exercise_dir(slug).is_dir():
		return []
	updated: list[str] = []
	intro = get_intro(slug)
	if intro and intro != (exercise.intro_markdown or "").strip():
		exercise.intro_markdown = intro
		updated.append("intro_markdown")
	soft = get_soft_skill(slug)
	if soft and soft != (exercise.soft_skill_prompt or "").strip():
		exercise.soft_skill_prompt = soft
		updated.append("soft_skill_prompt")
	graphic = get_graphic_markup(slug)
	if graphic and graphic != (exercise.graphic_markup or "").strip():
		exercise.graphic_markup = graphic
		updated.append("graphic_markup")
	merged = apply_messages_to_rules(slug, exercise.evaluation_rules)
	if merged != (exercise.evaluation_rules or {}):
		exercise.evaluation_rules = merged
		updated.append("evaluation_rules")
	return updated
