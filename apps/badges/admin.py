from django.contrib import admin

from .models import Badge, BadgeActivity, UserBadge, UserBadgeStats


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "threshold", "sort_order", "is_repeatable", "is_active")
    list_filter = ("category", "is_repeatable", "is_active")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ("user", "badge", "earned_at")
    list_filter = ("badge__category", "badge__is_repeatable", "badge")
    search_fields = ("user__username", "user__token", "badge__slug")


@admin.register(BadgeActivity)
class BadgeActivityAdmin(admin.ModelAdmin):
    list_display = ("user", "event_type", "exercise", "session_key", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("user__username", "user__token", "session_key")


@admin.register(UserBadgeStats)
class UserBadgeStatsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "exercises_completed_count",
        "consecutive_error_free_completions",
        "forum_posts_count",
        "platform_seconds",
        "updated_at",
    )
