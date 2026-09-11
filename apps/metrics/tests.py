from django.test import TestCase
from django.urls import reverse

from .models import AnonymousUsageEvent


class AnonymousMetricsTests(TestCase):
	def test_record_events_creates_anonymous_rows(self):
		response = self.client.post(
			reverse("metrics:record_events"),
			data={
				"anonymous_id": "11111111-2222-3333-4444-555555555555",
				"events": [
					{
						"event_type": "page_view",
						"path": "/exercises/pandas-introduction/",
						"exercise_slug": "pandas-introduction",
						"properties": {"referrer": "nav"},
					},
					{
						"event_type": "code_run",
						"path": "/exercises/pandas-introduction/",
						"exercise_slug": "pandas-introduction",
						"properties": {"success": True, "cell_count": 2},
					},
				],
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		payload = response.json()
		self.assertTrue(payload["success"])
		self.assertEqual(payload["recorded"], 2)
		self.assertEqual(AnonymousUsageEvent.objects.count(), 2)
		event = AnonymousUsageEvent.objects.filter(event_type="code_run").first()
		self.assertEqual(event.exercise_slug, "pandas-introduction")
		self.assertTrue(event.properties.get("success"))

	def test_record_events_rejects_invalid_anonymous_id(self):
		response = self.client.post(
			reverse("metrics:record_events"),
			data={
				"anonymous_id": "not-valid!!!",
				"events": [{"event_type": "page_view", "path": "/"}],
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 400)
		self.assertEqual(AnonymousUsageEvent.objects.count(), 0)

	def test_record_events_ignores_disallowed_event_types(self):
		response = self.client.post(
			reverse("metrics:record_events"),
			data={
				"anonymous_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
				"events": [
					{"event_type": "tracking_pixel", "path": "/hack"},
					{"event_type": "heartbeat", "path": "/courses/", "properties": {"active_ms": 15000}},
				],
			},
			content_type="application/json",
		)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json()["recorded"], 1)
		self.assertEqual(AnonymousUsageEvent.objects.count(), 1)
