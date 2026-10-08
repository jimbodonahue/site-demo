"""Shared Markdown → sanitized HTML for templates."""

from __future__ import annotations

from markdown import markdown
from django.utils.safestring import mark_safe
import bleach

MARKDOWN_EXTENSIONS = ["fenced_code", "tables", "sane_lists"]

ALLOWED_TAGS = [
	"p",
	"strong",
	"b",
	"em",
	"i",
	"ul",
	"ol",
	"li",
	"blockquote",
	"code",
	"pre",
	"table",
	"thead",
	"tbody",
	"tr",
	"th",
	"td",
	"a",
	"hr",
	"br",
	"h1",
	"h2",
	"h3",
	"h4",
	"h5",
	"h6",
]

ALLOWED_ATTRIBUTES = {
	"a": ["href", "title", "rel"],
	"code": ["class"],
}

ALLOWED_PROTOCOLS = ["http", "https", "mailto"]


def render_markdown_html(source: str | None) -> str:
	"""Convert Markdown to bleach-sanitized HTML (safe for |safe in templates)."""
	text = (source or "").strip()
	if not text:
		return ""
	html = markdown(text, extensions=MARKDOWN_EXTENSIONS)
	sanitized = bleach.clean(
		html,
		tags=ALLOWED_TAGS,
		attributes=ALLOWED_ATTRIBUTES,
		protocols=ALLOWED_PROTOCOLS,
		strip=True,
	)
	return mark_safe(sanitized)
