"""Rate limiting helpers for expensive exercise endpoints."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache


def _client_ip(request) -> str:
	forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
	if forwarded:
		return forwarded
	return request.META.get("REMOTE_ADDR") or "unknown"


def check_rate_limit(
	request,
	*,
	action: str,
	limit: int | None = None,
	window_seconds: int | None = None,
) -> tuple[bool, int]:
	"""Return (allowed, retry_after_seconds).

	Uses a fixed window counter in the default cache backend.
	"""
	limit = int(limit if limit is not None else getattr(settings, "EXERCISE_RUN_RATE_LIMIT", 30))
	window_seconds = int(
		window_seconds
		if window_seconds is not None
		else getattr(settings, "EXERCISE_RUN_RATE_WINDOW", 60)
	)
	session_key = getattr(request.session, "session_key", None) or "anon"
	identity = f"{session_key}:{_client_ip(request)}"
	cache_key = f"rate:{action}:{identity}"
	count = cache.get(cache_key)
	if count is None:
		cache.set(cache_key, 1, timeout=window_seconds)
		return True, 0
	if int(count) >= limit:
		return False, window_seconds
	try:
		cache.incr(cache_key)
	except ValueError:
		cache.set(cache_key, int(count) + 1, timeout=window_seconds)
	return True, 0
