"""Helpers for forum participation and suspension checks."""

from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.shortcuts import redirect
from django.utils import timezone

from apps.authentication.connections import create_notification
from apps.authentication.models import Notification


def forum_participation_allowed(user) -> bool:
    return bool(user and getattr(user, "can_use_forum", lambda: True)())


def reject_suspended_participant(request, user, *, next_url: str = "forum:code_of_conduct"):
    """Return a redirect response if the user cannot participate; else None."""
    if forum_participation_allowed(user):
        return None
    messages.error(
        request,
        "Your forum access is suspended. You can still practice exercises and "
        "submit a confidential Alert Admin report if you need help.",
    )
    return redirect(next_url)


def set_forum_suspension(user, *, moderator, days: int | None = None, note: str = "") -> None:
    user.is_forum_suspended = True
    user.forum_suspended_until = (
        timezone.now() + timedelta(days=int(days)) if days and int(days) > 0 else None
    )
    user.forum_suspension_note = (note or "").strip()
    user.save(
        update_fields=[
            "is_forum_suspended",
            "forum_suspended_until",
            "forum_suspension_note",
            "updated_at",
        ]
    )
    until_text = (
        f" until {user.forum_suspended_until:%Y-%m-%d %H:%M UTC}"
        if user.forum_suspended_until
        else " indefinitely"
    )
    if user.pk != getattr(moderator, "pk", None):
        create_notification(
            recipient=user,
            actor=moderator,
            notification_type=Notification.TYPE_FORUM_VIOLATION,
            message=(
                f"Your forum access has been suspended{until_text}. "
                "You can still use exercises. Review the Code of Conduct, and use "
                "Alert Admin if you believe this was a mistake."
            ),
        )


def clear_forum_suspension(user, *, moderator=None) -> None:
    user.is_forum_suspended = False
    user.forum_suspended_until = None
    user.forum_suspension_note = ""
    user.save(
        update_fields=[
            "is_forum_suspended",
            "forum_suspended_until",
            "forum_suspension_note",
            "updated_at",
        ]
    )
    if moderator is not None and user.pk != getattr(moderator, "pk", None):
        create_notification(
            recipient=user,
            actor=moderator,
            notification_type=Notification.TYPE_FORUM_VIOLATION,
            message=(
                "Your forum access has been restored. Please follow the Code of Conduct "
                "so everyone can keep learning together."
            ),
        )
