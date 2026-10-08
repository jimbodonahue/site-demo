"""Learner-facing exercise copy and prompt templates.

Edit files under ``content/exercises/<slug>/`` and ``content/prompts/``
rather than hard-coding strings in Python modules or migrations.
"""

from apps.exercises.content.loader import (
	apply_messages_to_rules,
	exercise_dir,
	get_graphic_markup,
	get_intro,
	get_messages,
	get_soft_skill,
	get_starter_code,
	load_json,
	load_prompt,
	load_text,
	render_prompt,
	sync_exercise_from_content,
)

__all__ = [
	"apply_messages_to_rules",
	"exercise_dir",
	"get_graphic_markup",
	"get_intro",
	"get_messages",
	"get_soft_skill",
	"get_starter_code",
	"load_json",
	"load_prompt",
	"load_text",
	"render_prompt",
	"sync_exercise_from_content",
]
