"""Account deletion requests, admin notification, and 48-hour auto-purge."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .models import AccountDeletionRequest, CustomUser

logger = logging.getLogger(__name__)

DELETION_GRACE_HOURS = 48


def _feedback_recipient() -> str:
    explicit = getattr(settings, "FEEDBACK_TO_EMAIL", None) or ""
    if explicit:
        return explicit
    admins = getattr(settings, "ADMINS", None) or []
    if admins:
        return admins[0][1]
    return getattr(settings, "DEFAULT_FROM_EMAIL", None) or "admin@localhost"


def schedule_account_deletion(
    user: CustomUser,
    *,
    reason: str,
    details: str = "",
    feedback: str = "",
    user_agent: str = "",
) -> AccountDeletionRequest:
    """Create a pending deletion request, deactivate the user, and email admins."""
    if user.is_staff or user.is_superuser:
        raise ValueError("Staff and superuser accounts cannot be deleted via this form.")

    existing = (
        AccountDeletionRequest.objects.filter(
            user=user,
            status=AccountDeletionRequest.STATUS_PENDING,
        )
        .order_by("-requested_at")
        .first()
    )
    if existing:
        return existing

    now = timezone.now()
    display_name = user.get_display_name()
    token_hint = (user.token or "")[:8]
    request_row = AccountDeletionRequest.objects.create(
        user=user,
        display_name=display_name,
        token_hint=token_hint,
        reason=reason,
        details=(details or "").strip(),
        feedback=(feedback or "").strip(),
        scheduled_delete_at=now + timedelta(hours=DELETION_GRACE_HOURS),
        user_agent=(user_agent or "")[:300],
    )

    user.is_active = False
    user.save(update_fields=["is_active", "updated_at"])

    if send_deletion_request_email(request_row):
        request_row.email_sent = True
        request_row.save(update_fields=["email_sent"])

    return request_row


def send_deletion_request_email(request_row: AccountDeletionRequest) -> bool:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
    to_email = _feedback_recipient()
    reason_label = request_row.get_reason_display()
    subject = "Account deletion request"
    body_lines = [
        "A member requested account deletion.",
        "",
        f"Request id: {request_row.pk}",
        f"Display name: {request_row.display_name or '(unknown)'}",
        f"Token hint: {request_row.token_hint or '(none)'}...",
        f"User id: {request_row.user_id or '(already removed)'}",
        f"Reason: {reason_label}",
        f"Requested at: {request_row.requested_at:%Y-%m-%d %H:%M UTC}",
        f"Auto-delete at: {request_row.scheduled_delete_at:%Y-%m-%d %H:%M UTC}",
        f"User agent: {request_row.user_agent or '(not provided)'}",
        "",
        "Details:",
        request_row.details or "(none)",
        "",
        "Feedback / complaints:",
        request_row.feedback or "(none)",
        "",
        "Delete the user manually in Admin within 48 hours if you prefer,",
        "or leave it — pending requests are purged automatically after the deadline.",
        "Admin → Authentication → Account deletion requests.",
    ]
    mail = EmailMessage(
        subject=subject,
        body="\n".join(body_lines),
        from_email=from_email,
        to=[to_email],
    )
    try:
        mail.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to email account deletion request %s", request_row.pk)
        return False


def complete_account_deletion(
    request_row: AccountDeletionRequest,
    *,
    completed_by: str = "auto",
) -> bool:
    """Delete the linked user (and cascaded data) and mark the request completed."""
    if request_row.status != AccountDeletionRequest.STATUS_PENDING:
        return False

    with transaction.atomic():
        locked = (
            AccountDeletionRequest.objects.select_for_update()
            .filter(pk=request_row.pk, status=AccountDeletionRequest.STATUS_PENDING)
            .first()
        )
        if locked is None:
            return False

        user = locked.user
        if user is not None and not (user.is_staff or user.is_superuser):
            user_id = user.pk
            user.delete()
            logger.info(
                "Deleted user %s via account deletion request %s (%s)",
                user_id,
                locked.pk,
                completed_by,
            )
        elif user is not None:
            logger.warning(
                "Skipping deletion of staff/superuser %s on request %s",
                user.pk,
                locked.pk,
            )
            locked.status = AccountDeletionRequest.STATUS_CANCELLED
            locked.completed_at = timezone.now()
            locked.completed_by = completed_by
            locked.save(update_fields=["status", "completed_at", "completed_by"])
            return False

        locked.user = None
        locked.status = AccountDeletionRequest.STATUS_COMPLETED
        locked.completed_at = timezone.now()
        locked.completed_by = completed_by
        locked.save(update_fields=["user", "status", "completed_at", "completed_by"])
    return True


def process_due_account_deletions(*, limit: int = 100) -> int:
    """Delete accounts whose 48-hour grace period has elapsed. Returns count completed."""
    now = timezone.now()
    due_ids = list(
        AccountDeletionRequest.objects.filter(
            status=AccountDeletionRequest.STATUS_PENDING,
            scheduled_delete_at__lte=now,
        )
        .order_by("scheduled_delete_at")
        .values_list("pk", flat=True)[:limit]
    )
    completed = 0
    for pk in due_ids:
        row = AccountDeletionRequest.objects.filter(pk=pk).first()
        if row and complete_account_deletion(row, completed_by="auto"):
            completed += 1
    return completed


def maybe_process_due_account_deletions(*, limit: int = 20, throttle_seconds: int = 300) -> int:
    """
    Opportunistically purge due deletions at most once per throttle window.
    Safe to call from request paths; use the management command for guaranteed cron runs.
    """
    from django.core.cache import cache

    if not cache.add("auth_purge_account_deletions", "1", timeout=throttle_seconds):
        return 0
    return process_due_account_deletions(limit=limit)
