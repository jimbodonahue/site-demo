"""Forum-specific Markdown rendering (code snippets behind spoilers)."""

from __future__ import annotations

import re
from html import escape

from bleach import clean
from django.utils.safestring import mark_safe
from markdown import markdown

from apps.exercises.markdown_utils import (
	ALLOWED_ATTRIBUTES,
	ALLOWED_PROTOCOLS,
	ALLOWED_TAGS,
	MARKDOWN_EXTENSIONS,
)

CODE_SPOILER_TOOLTIP = "Tips are good, but writing your own code builds muscles faster!"

_FORUM_TAGS = list(ALLOWED_TAGS) + ["details", "summary"]
_FORUM_ATTRIBUTES = {
	**ALLOWED_ATTRIBUTES,
	"details": ["class", "title"],
	"summary": ["class", "title"],
	"pre": ["class"],
}

_PRE_BLOCK_RE = re.compile(r"<pre(\s[^>]*)?>.*?</pre>", re.IGNORECASE | re.DOTALL)


def wrap_code_blocks_as_spoilers(html: str) -> str:
	"""Wrap each fenced/code ``<pre>`` block in a collapsed spoiler details element."""

	def _replace(match: re.Match[str]) -> str:
		pre_html = match.group(0)
		# Avoid double-wrapping if content already lives inside a spoiler.
		tooltip = escape(CODE_SPOILER_TOOLTIP, quote=True)
		return (
			f'<details class="forum-code-spoiler" title="{tooltip}">'
			f'<summary class="forum-code-spoiler-summary" title="{tooltip}">'
			f"Show code snippet"
			f"</summary>"
			f"{pre_html}"
			f"</details>"
		)

	return _PRE_BLOCK_RE.sub(_replace, html or "")


def render_forum_markdown_html(source: str | None) -> str:
	"""Render forum post Markdown; fenced code blocks are spoilers by default."""
	text = (source or "").strip()
	if not text:
		return ""
	html = markdown(text, extensions=MARKDOWN_EXTENSIONS)
	html = wrap_code_blocks_as_spoilers(html)
	sanitized = clean(
		html,
		tags=_FORUM_TAGS,
		attributes=_FORUM_ATTRIBUTES,
		protocols=ALLOWED_PROTOCOLS,
		strip=True,
	)
	return mark_safe(sanitized)
