from django.contrib import admin

from .models import Exercise, ExerciseAttempt, Track


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
	list_display = ("title", "order", "published", "is_placeholder", "updated_at")
	list_filter = ("published", "is_placeholder")
	search_fields = ("title", "slug", "summary")
	prepopulated_fields = {"slug": ("title",)}


@admin.register(Exercise)
class ExerciseAdmin(admin.ModelAdmin):
	list_display = ("title", "track", "order", "published", "is_placeholder", "updated_at")
	list_filter = ("published", "is_placeholder", "track")
	search_fields = ("title", "slug", "intro_markdown", "starter_code", "soft_skill_prompt")
	prepopulated_fields = {"slug": ("title",)}
	fields = (
		"track",
		"title",
		"slug",
		"intro_markdown",
		"soft_skill_prompt",
		"starter_code",
		"allowed_imports",
		"data_definition",
		"evaluation_rules",
		"graphic_markup",
		"order",
		"published",
		"is_placeholder",
	)


@admin.register(ExerciseAttempt)
class ExerciseAttemptAdmin(admin.ModelAdmin):
	list_display = ("exercise", "visitor_key", "created_at", "updated_at")
	list_filter = ("exercise",)
	search_fields = ("exercise__title", "visitor_key")
