"""Helpers for user connections, blocks, and ephemeral contact sharing."""

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from .models import Connection, ContactShareCooldown, Notification, UserBlock

CONTACT_SHARE_COOLDOWN = timedelta(hours=72)


def is_blocked_either_way(user_a, user_b) -> bool:
    if not user_a or not user_b or user_a.pk == user_b.pk:
        return False
    return UserBlock.objects.filter(
        Q(blocker=user_a, blocked=user_b) | Q(blocker=user_b, blocked=user_a)
    ).exists()


def has_blocked(blocker, blocked) -> bool:
    if not blocker or not blocked:
        return False
    return UserBlock.objects.filter(blocker=blocker, blocked=blocked).exists()


def get_connection_between(user_a, user_b):
    if not user_a or not user_b:
        return None
    return (
        Connection.objects.filter(
            Q(requester=user_a, recipient=user_b) | Q(requester=user_b, recipient=user_a)
        )
        .order_by("-created_at")
        .first()
    )


def users_are_connected(user_a, user_b) -> bool:
    connection = get_connection_between(user_a, user_b)
    return bool(connection and connection.status == Connection.STATUS_ACCEPTED)


def create_notification(
    *,
    recipient,
    actor,
    notification_type,
    connection=None,
    contact_payload="",
    message="",
):
    return Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        connection=connection,
        contact_payload=contact_payload or "",
        message=message or "",
    )


def contact_share_allowed(sender, recipient):
    """Return (allowed: bool, retry_after: datetime|None). Does not expose block status."""
    if is_blocked_either_way(sender, recipient):
        return False, None
    if not users_are_connected(sender, recipient):
        return False, None

    cooldown = ContactShareCooldown.objects.filter(sender=sender, recipient=recipient).first()
    if not cooldown:
        return True, None

    retry_after = cooldown.last_sent_at + CONTACT_SHARE_COOLDOWN
    if timezone.now() >= retry_after:
        return True, None
    return False, retry_after


def record_contact_share_cooldown(sender, recipient):
    ContactShareCooldown.objects.update_or_create(
        sender=sender,
        recipient=recipient,
        defaults={"last_sent_at": timezone.now()},
    )


def apply_block(blocker, blocked):
    """Block a user silently from their perspective. Tears down connection state."""
    if blocker.pk == blocked.pk:
        return None

    block, _ = UserBlock.objects.get_or_create(blocker=blocker, blocked=blocked)

    Connection.objects.filter(
        Q(requester=blocker, recipient=blocked) | Q(requester=blocked, recipient=blocker)
    ).delete()

    Notification.objects.filter(
        Q(recipient=blocker, actor=blocked) | Q(recipient=blocked, actor=blocker)
    ).update(contact_payload="", is_read=True)

    ContactShareCooldown.objects.filter(
        Q(sender=blocker, recipient=blocked) | Q(sender=blocked, recipient=blocker)
    ).delete()

    return block


def remove_block(blocker, blocked):
    UserBlock.objects.filter(blocker=blocker, blocked=blocked).delete()
