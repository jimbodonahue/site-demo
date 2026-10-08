import json
import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from project_core.ratelimit import check_rate_limit

from .models import AnonymousUsageEvent

ALLOWED_EVENT_TYPES = {choice[0] for choice in AnonymousUsageEvent.EVENT_CHOICES}
ANON_ID_RE = re.compile(r"^[0-9a-fA-F-]{8,64}$")
MAX_EVENTS_PER_REQUEST = 40
MAX_PROPERTY_KEYS = 20
MAX_STRING_LEN = 200


def _sanitize_properties(raw) -> dict:
	if not isinstance(raw, dict):
		return {}
	cleaned = {}
	for index, (key, value) in enumerate(raw.items()):
		if index >= MAX_PROPERTY_KEYS:
			break
		if not isinstance(key, str) or len(key) > 40:
			continue
		if isinstance(value, bool) or value is None:
			cleaned[key] = value
		elif isinstance(value, (int, float)):
			if abs(value) > 10**12:
				continue
			cleaned[key] = value
		elif isinstance(value, str):
			cleaned[key] = value[:MAX_STRING_LEN]
		elif isinstance(value, list) and len(value) <= 10:
			cleaned[key] = [
				item[:MAX_STRING_LEN] if isinstance(item, str) else item
				for item in value
				if isinstance(item, (str, int, float, bool)) or item is None
			]
	return cleaned


@csrf_exempt
@require_POST
def record_events(request):
	"""Accept a batch of anonymous usage events. No authentication required.

	CSRF is exempt so page-leave beacons can flush reliably. Events are anonymous,
	validated, capped per request, and rate limited per IP so the table cannot be
	flooded by an unauthenticated client.
	"""
	allowed, retry_after = check_rate_limit(
		request,
		action="metrics_ingest",
		limit=getattr(settings, "METRICS_RATE_LIMIT", 60),
		window_seconds=getattr(settings, "METRICS_RATE_WINDOW", 60),
		by_ip_only=True,
	)
	if not allowed:
		return JsonResponse(
			{"success": False, "error": "Too many events.", "retry_after": retry_after},
			status=429,
		)

	try:
		payload = json.loads(request.body or b"{}")
	except json.JSONDecodeError:
		return JsonResponse({"success": False, "error": "Invalid JSON."}, status=400)

	anonymous_id = str(payload.get("anonymous_id") or "").strip()
	if not ANON_ID_RE.match(anonymous_id):
		return JsonResponse({"success": False, "error": "Invalid anonymous_id."}, status=400)

	events = payload.get("events") or []
	if not isinstance(events, list) or not events:
		return JsonResponse({"success": False, "error": "No events provided."}, status=400)

	to_create = []
	for event in events[:MAX_EVENTS_PER_REQUEST]:
		if not isinstance(event, dict):
			continue
		event_type = str(event.get("event_type") or "").strip()
		if event_type not in ALLOWED_EVENT_TYPES:
			continue
		path = str(event.get("path") or "")[:255]
		exercise_slug = str(event.get("exercise_slug") or "")[:200]
		to_create.append(
			AnonymousUsageEvent(
				anonymous_id=anonymous_id,
				event_type=event_type,
				path=path,
				exercise_slug=exercise_slug,
				properties=_sanitize_properties(event.get("properties")),
			)
		)

	if not to_create:
		return JsonResponse({"success": False, "error": "No valid events."}, status=400)

	AnonymousUsageEvent.objects.bulk_create(to_create)

	# Signed-in learners also accrue platform time for one-time engagement badges.
	user = getattr(request, "user", None)
	if user is not None and getattr(user, "is_authenticated", False):
		presence_events = {
			AnonymousUsageEvent.EVENT_HEARTBEAT,
			AnonymousUsageEvent.EVENT_PAGE_VIEW,
			AnonymousUsageEvent.EVENT_PAGE_LEAVE,
			AnonymousUsageEvent.EVENT_CODE_RUN,
			AnonymousUsageEvent.EVENT_EVALUATE,
		}
		if any(event.event_type in presence_events for event in to_create):
			from apps.badges.services import record_platform_presence

			record_platform_presence(user)

	return JsonResponse({"success": True, "recorded": len(to_create)})
