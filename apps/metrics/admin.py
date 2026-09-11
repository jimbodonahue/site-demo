from django.contrib import admin

from .models import AnonymousUsageEvent


@admin.register(AnonymousUsageEvent)
class AnonymousUsageEventAdmin(admin.ModelAdmin):
	list_display = ("event_type", "path", "exercise_slug", "anonymous_id", "created_at")
	list_filter = ("event_type", "exercise_slug", "created_at")
	search_fields = ("anonymous_id", "path", "exercise_slug")
	readonly_fields = ("anonymous_id", "event_type", "path", "exercise_slug", "properties", "created_at")
	ordering = ("-created_at",)
