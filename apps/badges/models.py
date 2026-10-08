from django.conf import settings
from django.db import models


def _default_json_dict():
    return {}


class Badge(models.Model):
    """Catalog entry for an earnable badge."""

    CATEGORY_EXERCISES = "exercises"
    CATEGORY_STREAKS = "streaks"
    CATEGORY_FORUM = "forum"
    CATEGORY_CHOICES = [
        (CATEGORY_EXERCISES, "Exercises"),
        (CATEGORY_STREAKS, "Streaks & Speed"),
        (CATEGORY_FORUM, "Forum"),
    ]

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField()
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES, db_index=True)
    icon = models.CharField(max_length=16, default="🏅", help_text="Emoji shown on the badge card.")
    threshold = models.PositiveIntegerField(
        default=1,
        help_text="Numeric threshold used by award rules (e.g. completions required).",
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_repeatable = models.BooleanField(
        default=False,
        help_text="When true, this badge can be earned multiple times (e.g. every exercise completion).",
    )

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    """A badge award instance for a specific user.

    One-time badges should only have a single row per user; repeatable badges
    may have many rows (one per earn event).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="badges",
    )
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name="awards")
    earned_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=_default_json_dict, blank=True)

    class Meta:
        ordering = ["-earned_at"]
        indexes = [
            models.Index(fields=["user", "badge"]),
        ]

    def __str__(self):
        return f"{self.user} → {self.badge.slug}"


class BadgeActivity(models.Model):
    """Append-only activity log used to evaluate streak and daily badges."""

    EVENT_RUN_SUCCESS = "run_success"
    EVENT_RUN_ERROR = "run_error"
    EVENT_EXERCISE_PASSED = "exercise_passed"
    EVENT_FORUM_POST = "forum_post"
    EVENT_PLOT_BONUS = "plot_bonus"
    EVENT_CHOICES = [
        (EVENT_RUN_SUCCESS, "Run succeeded"),
        (EVENT_RUN_ERROR, "Run failed"),
        (EVENT_EXERCISE_PASSED, "Exercise passed"),
        (EVENT_FORUM_POST, "Forum post"),
        (EVENT_PLOT_BONUS, "Plotting bonus earned"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="badge_activities",
    )
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES, db_index=True)
    exercise = models.ForeignKey(
        "exercises.Exercise",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="badge_activities",
    )
    session_key = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=_default_json_dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Badge activities"

    def __str__(self):
        return f"{self.user_id}:{self.event_type}@{self.created_at:%Y-%m-%d %H:%M}"


class UserBadgeStats(models.Model):
    """Mutable counters that support streak-style badge rules."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="badge_stats",
    )
    consecutive_error_free_completions = models.PositiveIntegerField(default=0)
    exercises_completed_count = models.PositiveIntegerField(default=0)
    forum_posts_count = models.PositiveIntegerField(default=0)
    plots_created_count = models.PositiveIntegerField(default=0)
    plot_modifications_count = models.PositiveIntegerField(default=0)
    platform_seconds = models.PositiveIntegerField(
        default=0,
        help_text="Accumulated active time on the platform while signed in.",
    )
    last_seen_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last authenticated presence timestamp used for time accumulation.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Badge stats for {self.user}"
