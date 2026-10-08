"""Shared fixed-window rate limiting for expensive or credential endpoints."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
	"""Resolve the client IP, only trusting X-Forwarded-For behind known proxies.

	``TRUSTED_PROXY_COUNT`` is how many proxies append to the header in front of
	the app. The client address is that many hops from the right; anything
	further left is attacker-controlled and must not be used as a rate-limit key.
	"""
	remote_addr = request.META.get("REMOTE_ADDR") or "unknown"
	proxy_count = int(getattr(settings, "TRUSTED_PROXY_COUNT", 0) or 0)
	if proxy_count <= 0:
		return remote_addr

	forwarded = [
		part.strip()
		for part in (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")
		if part.strip()
	]
	if len(forwarded) < proxy_count:
		return remote_addr
	return forwarded[-proxy_count]


def check_rate_limit(
	request,
	*,
	action: str,
	limit: int | None = None,
	window_seconds: int | None = None,
	by_ip_only: bool = False,
) -> tuple[bool, int]:
	"""Return (allowed, retry_after_seconds).

	Uses a fixed window counter in the default cache backend. Set ``by_ip_only``
	for credential endpoints, where keying on the session would let an attacker
	reset the counter by dropping their cookie.
	"""
	limit = int(limit if limit is not None else getattr(settings, "EXERCISE_RUN_RATE_LIMIT", 30))
	window_seconds = int(
		window_seconds
		if window_seconds is not None
		else getattr(settings, "EXERCISE_RUN_RATE_WINDOW", 60)
	)
	ip = client_ip(request)
	if by_ip_only:
		identity = ip
	else:
		session_key = getattr(request.session, "session_key", None) or "anon"
		identity = f"{session_key}:{ip}"
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
