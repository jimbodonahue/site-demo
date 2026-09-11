from django.urls import path

from .views import record_events

app_name = "metrics"

urlpatterns = [
	path("events/", record_events, name="record_events"),
]
