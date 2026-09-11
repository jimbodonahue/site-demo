import json
import re

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

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
	validated, and capped per request.
	"""
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
	return JsonResponse({"success": True, "recorded": len(to_create)})
