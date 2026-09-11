from django.db import models


def _default_json_dict():
	return {}


class AnonymousUsageEvent(models.Model):
	"""First-party anonymous usage event. No personal identifiers are stored."""

	EVENT_PAGE_VIEW = "page_view"
	EVENT_HEARTBEAT = "heartbeat"
	EVENT_PAGE_LEAVE = "page_leave"
	EVENT_CODE_RUN = "code_run"
	EVENT_CODE_RESET = "code_reset"
	EVENT_EVALUATE = "evaluate"
	EVENT_FEATURE_SELECT = "feature_select"

	EVENT_CHOICES = [
		(EVENT_PAGE_VIEW, "Page view"),
		(EVENT_HEARTBEAT, "Heartbeat"),
		(EVENT_PAGE_LEAVE, "Page leave"),
		(EVENT_CODE_RUN, "Code run"),
		(EVENT_CODE_RESET, "Code reset"),
		(EVENT_EVALUATE, "Evaluate"),
		(EVENT_FEATURE_SELECT, "Feature select"),
	]

	anonymous_id = models.CharField(
		max_length=64,
		db_index=True,
		help_text="Client-generated random ID stored in localStorage. Not linked to accounts.",
	)
	event_type = models.CharField(max_length=32, choices=EVENT_CHOICES, db_index=True)
	path = models.CharField(max_length=255, blank=True, db_index=True)
	exercise_slug = models.SlugField(max_length=200, blank=True, db_index=True)
	properties = models.JSONField(default=_default_json_dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True, db_index=True)

	class Meta:
		ordering = ["-created_at"]
		indexes = [
			models.Index(fields=["event_type", "created_at"]),
			models.Index(fields=["exercise_slug", "event_type"]),
		]

	def __str__(self):
		return f"{self.event_type} @ {self.path or self.exercise_slug or 'unknown'}"
