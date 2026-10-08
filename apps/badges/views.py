from django.shortcuts import render

from apps.forum.views import get_or_create_forum_user

from .models import Badge
from .services import badge_award_summary, ensure_badge_catalog, record_platform_presence


def badge_gallery(request):
    """Show the full badge catalog and highlight badges earned by the current user."""
    ensure_badge_catalog()
    user, token = get_or_create_forum_user(request)
    record_platform_presence(user)
    badges = list(Badge.objects.filter(is_active=True))
    awards = badge_award_summary(user)
    grouped = {}
    for badge in badges:
        summary = awards.get(badge.pk) or {}
        grouped.setdefault(badge.category, []).append(
            {
                "badge": badge,
                "earned": summary.get("latest"),
                "earn_count": summary.get("count") or 0,
            }
        )

    category_labels = dict(Badge.CATEGORY_CHOICES)
    category_order = [key for key, _label in Badge.CATEGORY_CHOICES]
    sections = [
        {
            "key": key,
            "label": category_labels.get(key, key.title()),
            "items": grouped[key],
        }
        for key in category_order
        if key in grouped
    ]
    earned_count = sum(1 for summary in awards.values() if summary.get("count"))
    profile = getattr(user, "profile", None)
    profile_nickname = getattr(profile, "nickname", None) if profile and getattr(profile, "pk", None) else None
    return render(
        request,
        "badges/gallery.html",
        {
            "sections": sections,
            "earned_count": earned_count,
            "total_count": len(badges),
            "forum_user": user,
            "forum_token": token,
            "profile_nickname": profile_nickname,
        },
    )
