from __future__ import annotations

from django.db.models import Count
from django.utils import timezone

from apps.exercises.models import Exercise, ExerciseAttempt

from .catalog import BADGE_DEFINITIONS
from .models import Badge, BadgeActivity, UserBadge, UserBadgeStats

TEN_HOURS_SECONDS = 10 * 60 * 60
# Cap gaps so idle tabs / overnight pauses do not inflate platform time.
PLATFORM_PRESENCE_MAX_GAP_SECONDS = 120


def ensure_badge_catalog() -> None:
    for definition in BADGE_DEFINITIONS:
        Badge.objects.update_or_create(
            slug=definition["slug"],
            defaults={
                "name": definition["name"],
                "description": definition["description"],
                "category": definition["category"],
                "icon": definition["icon"],
                "threshold": definition["threshold"],
                "sort_order": definition["sort_order"],
                "is_active": True,
                "is_repeatable": bool(definition.get("is_repeatable", False)),
            },
        )


def _get_or_create_stats(user) -> UserBadgeStats:
    stats, _created = UserBadgeStats.objects.get_or_create(user=user)
    return stats


def award_badge(user, slug: str, metadata: dict | None = None) -> UserBadge | None:
    """Award a badge. Repeatable badges create a new row every time; others once."""
    if user is None or not getattr(user, "pk", None):
        return None
    badge = Badge.objects.filter(slug=slug, is_active=True).first()
    if not badge:
        return None
    payload = metadata or {}
    if badge.is_repeatable:
        return UserBadge.objects.create(user=user, badge=badge, metadata=payload)
    award, created = UserBadge.objects.get_or_create(
        user=user,
        badge=badge,
        defaults={"metadata": payload},
    )
    return award if created else None


def _completed_exercise_count(user) -> int:
    """Count distinct exercises this user has passed (for milestone badges)."""
    activity_count = (
        BadgeActivity.objects.filter(
            user=user,
            event_type=BadgeActivity.EVENT_EXERCISE_PASSED,
            exercise_id__isnull=False,
        )
        .values("exercise_id")
        .distinct()
        .count()
    )
    if activity_count:
        return activity_count

    # Fallback for legacy progress stored only on attempts.
    visitor_key = f"user:{user.pk}"
    count = 0
    for attempt in ExerciseAttempt.objects.filter(visitor_key=visitor_key).only("progress_state"):
        if bool((attempt.progress_state or {}).get("passed")):
            count += 1
    return count


def _session_key(request) -> str:
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ""


def _resolve_user(request):
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def record_platform_presence(user, *, now=None, max_gap_seconds: int = PLATFORM_PRESENCE_MAX_GAP_SECONDS) -> list[UserBadge]:
    """Credit signed-in active time and award one-time time badges when earned."""
    if user is None or not getattr(user, "pk", None):
        return []

    ensure_badge_catalog()
    stats = _get_or_create_stats(user)
    stamp = now or timezone.now()
    newly_awarded: list[UserBadge] = []

    if stats.last_seen_at:
        gap = (stamp - stats.last_seen_at).total_seconds()
        if 0 < gap <= max_gap_seconds:
            stats.platform_seconds = int(stats.platform_seconds or 0) + int(gap)

    stats.last_seen_at = stamp
    stats.save(update_fields=["platform_seconds", "last_seen_at", "updated_at"])

    if int(stats.platform_seconds or 0) >= TEN_HOURS_SECONDS:
        award = award_badge(
            user,
            "ten-hours",
            metadata={"platform_seconds": stats.platform_seconds},
        )
        if award:
            newly_awarded.append(award)
    return newly_awarded


def record_exercise_run(
    request,
    exercise: Exercise,
    *,
    ran: bool | None = None,
    core_passed: bool | None = None,
    success: bool | None = None,
    passed: bool | None = None,
    plotting_bonus: dict | None = None,
) -> list[UserBadge]:
    """Record a notebook evaluate and award newly earned exercise/streak badges.

    ``ran`` = executed without runtime errors.
    ``core_passed`` = academic core rubric passed.
    Legacy ``success``/``passed`` kwargs remain accepted aliases.
    """
    user = _resolve_user(request)
    if user is None:
        return []

    if ran is None:
        ran = bool(success) if success is not None else bool(passed)
    if core_passed is None:
        core_passed = bool(passed) if passed is not None else bool(success)

    ensure_badge_catalog()
    session_key = _session_key(request)
    stats = _get_or_create_stats(user)
    newly_awarded: list[UserBadge] = []
    newly_awarded.extend(record_platform_presence(user))

    prior_session_runs = BadgeActivity.objects.filter(
        user=user,
        exercise=exercise,
        session_key=session_key,
        event_type__in=[BadgeActivity.EVENT_RUN_SUCCESS, BadgeActivity.EVENT_RUN_ERROR],
    ).count()

    event_type = BadgeActivity.EVENT_RUN_SUCCESS if ran else BadgeActivity.EVENT_RUN_ERROR
    BadgeActivity.objects.create(
        user=user,
        event_type=event_type,
        exercise=exercise,
        session_key=session_key,
        metadata={"passed": bool(core_passed), "ran": bool(ran), "core_passed": bool(core_passed)},
    )

    if not ran:
        # Only runtime failures reset the flawless streak.
        stats.consecutive_error_free_completions = 0
        stats.save(update_fields=["consecutive_error_free_completions", "updated_at"])
    elif core_passed:
        # First attempt this session: no prior runs for this exercise in the session.
        if prior_session_runs == 0:
            award = award_badge(
                user,
                "first-try",
                metadata={"exercise": exercise.slug, "session_key": session_key},
            )
            if award:
                newly_awarded.append(award)

        BadgeActivity.objects.create(
            user=user,
            event_type=BadgeActivity.EVENT_EXERCISE_PASSED,
            exercise=exercise,
            session_key=session_key,
            metadata={"exercise": exercise.slug},
        )

        # Collectible: one award every successful completion.
        award = award_badge(
            user,
            "exercise-complete",
            metadata={"exercise": exercise.slug, "session_key": session_key},
        )
        if award:
            newly_awarded.append(award)

        completed_count = _completed_exercise_count(user)
        stats.exercises_completed_count = completed_count
        stats.consecutive_error_free_completions += 1
        stats.save(
            update_fields=[
                "exercises_completed_count",
                "consecutive_error_free_completions",
                "updated_at",
            ]
        )

        for slug, threshold in (
            ("first-exercise", 1),
            ("exercise-trio", 3),
            ("exercise-collector", 5),
        ):
            if completed_count >= threshold:
                award = award_badge(user, slug, metadata={"completed_count": completed_count})
                if award:
                    newly_awarded.append(award)

        if stats.consecutive_error_free_completions >= 5:
            award = award_badge(
                user,
                "flawless-five",
                metadata={"streak": stats.consecutive_error_free_completions},
            )
            if award:
                newly_awarded.append(award)

        today = timezone.localdate()
        daily_unique = len(
            {
                activity.exercise_id
                for activity in BadgeActivity.objects.filter(
                    user=user,
                    event_type=BadgeActivity.EVENT_EXERCISE_PASSED,
                    created_at__date=today,
                ).only("exercise_id")
                if activity.exercise_id
            }
        )
        if daily_unique >= 10:
            award = award_badge(
                user,
                "daily-ten",
                metadata={"date": str(today), "count": daily_unique},
            )
            if award:
                newly_awarded.append(award)

    # Plotting bonus is independent of main exercise pass/fail.
    bonus = plotting_bonus or {}
    if bool(bonus.get("passed")):
        plots_delta = int(bonus.get("plots_created") or 0)
        mods_delta = int(bonus.get("modifications_count") or 0)
        BadgeActivity.objects.create(
            user=user,
            event_type=BadgeActivity.EVENT_PLOT_BONUS,
            exercise=exercise,
            session_key=session_key,
            metadata={
                "kind": bonus.get("kind"),
                "plots_created": plots_delta,
                "modifications_count": mods_delta,
                "modification_categories": bonus.get("modification_categories") or [],
            },
        )
        stats.plots_created_count = (stats.plots_created_count or 0) + max(plots_delta, 0)
        stats.plot_modifications_count = (stats.plot_modifications_count or 0) + max(mods_delta, 0)
        stats.save(update_fields=["plots_created_count", "plot_modifications_count", "updated_at"])

        for slug, threshold in (
            ("first-plot", 1),
            ("plot-pack", 5),
            ("plot-gallery", 10),
        ):
            if stats.plots_created_count >= threshold:
                award = award_badge(
                    user,
                    slug,
                    metadata={"plots_created_count": stats.plots_created_count},
                )
                if award:
                    newly_awarded.append(award)

        for slug, threshold in (
            ("style-spark", 1),
            ("style-studio", 5),
            ("style-virtuoso", 10),
        ):
            if stats.plot_modifications_count >= threshold:
                award = award_badge(
                    user,
                    slug,
                    metadata={"plot_modifications_count": stats.plot_modifications_count},
                )
                if award:
                    newly_awarded.append(award)

    return newly_awarded


def record_forum_post(user, *, post_id: int | None = None) -> list[UserBadge]:
    if user is None or not getattr(user, "pk", None):
        return []
    ensure_badge_catalog()
    stats = _get_or_create_stats(user)
    newly_awarded: list[UserBadge] = []
    newly_awarded.extend(record_platform_presence(user))
    BadgeActivity.objects.create(
        user=user,
        event_type=BadgeActivity.EVENT_FORUM_POST,
        metadata={"post_id": post_id},
    )
    stats.forum_posts_count = (stats.forum_posts_count or 0) + 1
    stats.save(update_fields=["forum_posts_count", "updated_at"])

    award = award_badge(user, "forum-newcomer", metadata={"post_id": post_id})
    if award:
        newly_awarded.append(award)
    if stats.forum_posts_count >= 5:
        award = award_badge(user, "forum-regular", metadata={"posts": stats.forum_posts_count})
        if award:
            newly_awarded.append(award)
    return newly_awarded


def record_post_like_threshold(post, like_count: int) -> list[UserBadge]:
    if like_count < 5 or post is None or post.author_id is None:
        return []
    ensure_badge_catalog()
    award = award_badge(
        post.author,
        "well-received",
        metadata={"post_id": post.pk, "like_count": like_count},
    )
    return [award] if award else []


def badge_award_summary(user) -> dict[int, dict]:
    """Map badge_id → {count, latest} for gallery rendering."""
    if user is None or not getattr(user, "pk", None):
        return {}
    rows = (
        UserBadge.objects.filter(user=user)
        .values("badge_id")
        .annotate(count=Count("id"))
        .order_by()
    )
    latest_by_badge = {}
    for award in UserBadge.objects.filter(user=user).select_related("badge").order_by("-earned_at"):
        latest_by_badge.setdefault(award.badge_id, award)
    return {
        row["badge_id"]: {
            "count": row["count"],
            "latest": latest_by_badge.get(row["badge_id"]),
        }
        for row in rows
    }


def earned_badges_for_profile(user) -> list[dict]:
    """Earned badges for profile/membership display (newest first)."""
    if user is None or not getattr(user, "pk", None):
        return []
    ensure_badge_catalog()
    summary = badge_award_summary(user)
    items: list[dict] = []
    for badge in Badge.objects.filter(is_active=True).order_by("sort_order", "name"):
        row = summary.get(badge.pk)
        if not row or not row.get("count"):
            continue
        items.append(
            {
                "badge": badge,
                "earn_count": row["count"],
                "earned": row["latest"],
            }
        )
    items.sort(
        key=lambda item: item["earned"].earned_at if item.get("earned") else timezone.now(),
        reverse=True,
    )
    return items
