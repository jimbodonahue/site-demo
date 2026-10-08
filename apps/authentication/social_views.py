"""Public profiles, connections, contact sharing, and notifications."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.forum.views import get_or_create_forum_user

from .connections import (
    apply_block,
    contact_share_allowed,
    create_notification,
    get_connection_between,
    has_blocked,
    is_blocked_either_way,
    record_contact_share_cooldown,
    remove_block,
)
from .forms import ContactShareForm
from .models import Connection, Notification, UserProfile


def _viewer(request):
    user, _token = get_or_create_forum_user(request)
    return user


def _ensure_saved_profile(user):
    profile = getattr(user, "profile", None)
    if profile is None:
        profile = UserProfile(user=user, nickname=f"user-{user.pk}")
        profile.save()
    elif not profile.pk:
        profile.save()
    return profile


def public_profile(request, nickname):
    profile = get_object_or_404(
        UserProfile.objects.select_related("user"),
        nickname__iexact=nickname,
    )
    viewer = _viewer(request)
    target = profile.user
    is_own = viewer.pk == target.pk

    connection = None if is_own else get_connection_between(viewer, target)
    i_blocked_them = False if is_own else has_blocked(viewer, target)
    share_form = ContactShareForm()
    can_share = False
    share_retry_after = None
    if not is_own and connection and connection.status == Connection.STATUS_ACCEPTED:
        can_share, share_retry_after = contact_share_allowed(viewer, target)

    can_moderate_forum = bool(
        not is_own
        and (viewer.is_forum_moderator or viewer.is_staff)
        and not (target.is_forum_moderator or target.is_staff)
    )
    target_forum_suspended = not target.can_use_forum()

    from apps.badges.services import earned_badges_for_profile

    return render(
        request,
        "authentication/public_profile.html",
        {
            "profile": profile,
            "profile_user": target,
            "is_own_profile": is_own,
            "connection": connection,
            "i_blocked_them": i_blocked_them,
            "can_share": can_share,
            "share_retry_after": share_retry_after,
            "share_form": share_form,
            "can_moderate_forum": can_moderate_forum,
            "target_forum_suspended": target_forum_suspended,
            "earned_badges": earned_badges_for_profile(target),
        },
    )


@require_POST
def request_connection(request, nickname):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), nickname__iexact=nickname)
    viewer = _viewer(request)
    _ensure_saved_profile(viewer)
    target = profile.user

    if viewer.pk == target.pk:
        messages.error(request, "You cannot connect with yourself.")
        return redirect("public_profile", nickname=profile.nickname)

    existing = get_connection_between(viewer, target)
    if existing and existing.status == Connection.STATUS_ACCEPTED:
        messages.info(request, "You are already connected.")
        return redirect("public_profile", nickname=profile.nickname)
    if existing and existing.status == Connection.STATUS_PENDING:
        messages.info(request, "A connection request is already pending.")
        return redirect("public_profile", nickname=profile.nickname)

    # Silent when blocked: requester sees success and a pending state, but no notification is sent.
    if is_blocked_either_way(viewer, target):
        if not existing:
            Connection.objects.create(
                requester=viewer,
                recipient=target,
                status=Connection.STATUS_PENDING,
            )
        messages.success(request, "Connection request sent.")
        return redirect("public_profile", nickname=profile.nickname)

    if existing and existing.status == Connection.STATUS_DECLINED:
        existing.requester = viewer
        existing.recipient = target
        existing.status = Connection.STATUS_PENDING
        existing.responded_at = None
        existing.save()
        connection = existing
    else:
        connection = Connection.objects.create(
            requester=viewer,
            recipient=target,
            status=Connection.STATUS_PENDING,
        )

    create_notification(
        recipient=target,
        actor=viewer,
        notification_type=Notification.TYPE_CONNECTION_REQUEST,
        connection=connection,
    )
    messages.success(request, "Connection request sent.")
    return redirect("public_profile", nickname=profile.nickname)


@require_POST
def respond_connection(request, notification_id):
    viewer = _viewer(request)
    notification = get_object_or_404(
        Notification.objects.select_related("connection", "actor", "recipient"),
        pk=notification_id,
        recipient=viewer,
        notification_type=Notification.TYPE_CONNECTION_REQUEST,
    )
    connection = notification.connection
    action = request.POST.get("action")

    if not connection or connection.status != Connection.STATUS_PENDING:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        messages.info(request, "This connection request is no longer available.")
        return redirect("notifications")

    if is_blocked_either_way(viewer, connection.requester):
        connection.status = Connection.STATUS_DECLINED
        connection.responded_at = timezone.now()
        connection.save(update_fields=["status", "responded_at"])
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        messages.info(request, "This connection request is no longer available.")
        return redirect("notifications")

    if action == "accept":
        connection.status = Connection.STATUS_ACCEPTED
        connection.responded_at = timezone.now()
        connection.save(update_fields=["status", "responded_at"])
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        create_notification(
            recipient=connection.requester,
            actor=viewer,
            notification_type=Notification.TYPE_CONNECTION_ACCEPTED,
            connection=connection,
        )
        messages.success(request, "Connection accepted. You can now share contact details.")
    elif action == "decline":
        connection.status = Connection.STATUS_DECLINED
        connection.responded_at = timezone.now()
        connection.save(update_fields=["status", "responded_at"])
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        messages.info(request, "Connection request declined.")
    else:
        messages.error(request, "Unknown action.")

    return redirect("notifications")


@require_POST
def share_contact(request, nickname):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), nickname__iexact=nickname)
    viewer = _viewer(request)
    target = profile.user
    form = ContactShareForm(request.POST)

    if viewer.pk == target.pk:
        messages.error(request, "You cannot share contact details with yourself.")
        return redirect("public_profile", nickname=profile.nickname)

    if not form.is_valid():
        messages.error(request, "Please enter the contact details you want to share.")
        return redirect("public_profile", nickname=profile.nickname)

    allowed, retry_after = contact_share_allowed(viewer, target)
    if not allowed:
        # Generic copy — never disclose that the other person blocked them.
        if retry_after:
            messages.warning(
                request,
                "You can share contact details with this member again after "
                f"{retry_after.strftime('%Y-%m-%d %H:%M')} UTC.",
            )
        else:
            messages.error(request, "Unable to send contact details right now.")
        return redirect("public_profile", nickname=profile.nickname)

    connection = get_connection_between(viewer, target)
    create_notification(
        recipient=target,
        actor=viewer,
        notification_type=Notification.TYPE_CONTACT_SHARED,
        connection=connection,
        contact_payload=form.cleaned_data["contact_details"],
    )
    record_contact_share_cooldown(viewer, target)
    messages.success(
        request,
        "Contact details sent. They are not stored after the other person views them.",
    )
    return redirect("public_profile", nickname=profile.nickname)


@require_POST
def reveal_contact(request, notification_id):
    viewer = _viewer(request)
    notification = get_object_or_404(
        Notification,
        pk=notification_id,
        recipient=viewer,
        notification_type=Notification.TYPE_CONTACT_SHARED,
    )
    payload = notification.contact_payload
    notification.contact_payload = ""
    notification.is_read = True
    notification.save(update_fields=["contact_payload", "is_read"])

    if not payload:
        messages.info(
            request,
            "This contact information is no longer available. "
            "It was not kept after it was viewed.",
        )
        return redirect("notifications")

    return render(
        request,
        "authentication/contact_reveal.html",
        {
            "notification": notification,
            "contact_details": payload,
            "actor": notification.actor,
        },
    )


@require_POST
def block_user(request, nickname):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), nickname__iexact=nickname)
    viewer = _viewer(request)
    target = profile.user

    if viewer.pk == target.pk:
        messages.error(request, "You cannot block yourself.")
        return redirect("public_profile", nickname=profile.nickname)

    apply_block(viewer, target)
    messages.success(request, "Member blocked.")
    return redirect("public_profile", nickname=profile.nickname)


@require_POST
def unblock_user(request, nickname):
    profile = get_object_or_404(UserProfile.objects.select_related("user"), nickname__iexact=nickname)
    viewer = _viewer(request)
    target = profile.user
    remove_block(viewer, target)
    messages.success(request, "Member unblocked.")
    return redirect("public_profile", nickname=profile.nickname)


def notifications(request):
    viewer = _viewer(request)
    items = (
        Notification.objects.filter(recipient=viewer)
        .select_related("actor", "actor__profile", "connection")
        .order_by("-created_at")[:100]
    )
    Notification.objects.filter(
        recipient=viewer,
        is_read=False,
    ).exclude(notification_type=Notification.TYPE_CONTACT_SHARED).update(is_read=True)

    return render(
        request,
        "authentication/notifications.html",
        {"notifications": items},
    )
