import json
import logging
import re
import secrets

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.core.mail import EmailMessage
from django.db.models import Count, Exists, OuterRef
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods, require_POST

from apps.authentication.models import CustomUser, UserProfile
from .access import (
    clear_forum_suspension,
    forum_participation_allowed,
    reject_suspended_participant,
    set_forum_suspension,
)
from .forms import ConductReportForm
from .models import ForumConductReport, Post, PostLike, Topic
from .utils import RESOURCES_WIKI_TOPICS, ensure_forum_topics

logger = logging.getLogger(__name__)


class PostForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(
            attrs={"rows": 4, "placeholder": "Write your reply...", "class": "w-full rounded-2xl border border-slate-300 p-4 text-slate-900 focus:border-sky-500 focus:outline-none"}
        ),
        label="Reply",
    )


def get_or_create_forum_user(request):
    """
    Retrieves or creates a token-identified user for forum participation.
    No personal information (email, name, password) is required.
    """
    from apps.authentication.deletion import maybe_process_due_account_deletions

    maybe_process_due_account_deletions()
    token = request.session.get("forum_token")
    if token:
        user = CustomUser.objects.filter(token=token).first()
        if user and not user.is_active:
            request.session.pop("forum_token", None)
            user = None
        if user:
            if not request.user.is_authenticated or request.user != user:
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            return user, token

    if request.user.is_authenticated and not request.user.is_active:
        logout(request)
        request.session.pop("forum_token", None)

    if request.user.is_authenticated and request.user.is_active:
        user = request.user
        if not user.token:
            user.token = secrets.token_hex(16)
            if not user.username:
                user.username = f"Anon-{user.token[:6]}"
            user.save(update_fields=["token", "username"])
        token = user.token
        request.session["forum_token"] = token
        return user, token

    user, _ = CustomUser.objects.get_or_create_token_user()
    token = user.token
    request.session["forum_token"] = token
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return user, token


def topic_list(request):
    """List forum topics grouped into Exercise Discussions, Resources wiki, and community spaces."""
    ensure_forum_topics()
    user, token = get_or_create_forum_user(request)
    topics = (
        Topic.objects.select_related("created_by", "created_by__profile", "exercise")
        .annotate(post_count=Count("posts"))
        .order_by("title")
    )

    resource_order = {title: index for index, (title, _intro) in enumerate(RESOURCES_WIKI_TOPICS)}
    resource_topics = sorted(
        [topic for topic in topics if topic.section == Topic.SECTION_RESOURCES],
        key=lambda topic: (resource_order.get(topic.title, 999), topic.title.lower()),
    )
    exercise_topics = sorted(
        [topic for topic in topics if topic.section == Topic.SECTION_EXERCISE],
        key=lambda topic: ((topic.exercise.order if topic.exercise else 0), topic.title.lower()),
    )
    job_market_topic = next((topic for topic in topics if topic.section == Topic.SECTION_JOB_MARKET), None)
    achievements_topic = next(
        (topic for topic in topics if topic.section == Topic.SECTION_ACHIEVEMENTS), None
    )
    other_topics = sorted(
        [topic for topic in topics if topic.section == Topic.SECTION_GENERAL],
        key=lambda topic: topic.created_at,
        reverse=True,
    )

    return render(
        request,
        "forum/topic_list.html",
        {
            "resource_topics": resource_topics,
            "exercise_topics": exercise_topics,
            "job_market_topic": job_market_topic,
            "achievements_topic": achievements_topic,
            "other_topics": other_topics,
            "forum_user": user,
            "forum_token": token,
            "forum_suspended": not forum_participation_allowed(user),
            "is_forum_moderator": bool(user.is_forum_moderator or user.is_staff),
        },
    )


def topic_create(request):
    """Create a new generic topic without requiring email login."""
    user, token = get_or_create_forum_user(request)
    blocked = reject_suspended_participant(request, user)
    if blocked:
        return blocked
    if request.method == "POST":
        title = request.POST.get("title")
        if title:
            topic = Topic.objects.create(title=title, created_by=user)
            return redirect(topic.get_absolute_url())
    return render(
        request,
        "forum/topic_form.html",
        {
            "exercise": None,
            "forum_user": user,
            "forum_token": token,
            "forum_suspended": not forum_participation_allowed(user),
        },
    )


def exercise_topic_create(request, exercise_slug):
    """Create or jump to a topic linked to a specific exercise without requiring email login."""
    from apps.exercises.models import Exercise

    ensure_forum_topics()
    user, token = get_or_create_forum_user(request)
    exercise = get_object_or_404(Exercise, slug=exercise_slug, published=True)

    existing_topic = Topic.objects.filter(exercise=exercise).first()
    if existing_topic and request.method == "GET":
        return redirect(existing_topic.get_absolute_url())

    if request.method == "POST":
        blocked = reject_suspended_participant(request, user)
        if blocked:
            return blocked
        title = request.POST.get("title") or f"Discussion: {exercise.title}"
        if existing_topic:
            return redirect(existing_topic.get_absolute_url())
        topic = Topic.objects.create(
            title=title, created_by=user, exercise=exercise
        )
        return redirect(topic.get_absolute_url())
    return render(
        request,
        "forum/topic_form.html",
        {
            "exercise": exercise,
            "forum_user": user,
            "forum_token": token,
            "forum_suspended": not forum_participation_allowed(user),
        },
    )


def topic_detail(request, pk):
    """Show a topic and its posts; allow posting a new reply using token identity."""
    user, token = get_or_create_forum_user(request)
    topic = get_object_or_404(Topic, pk=pk)
    liked_by_user = PostLike.objects.filter(post_id=OuterRef("pk"), user=user)
    posts = (
        topic.posts.select_related("author", "author__profile")
        .annotate(
            annotated_like_count=Count("likes", distinct=True),
            user_has_liked=Exists(liked_by_user),
        )
    )
    can_participate = forum_participation_allowed(user)
    if request.method == "POST":
        blocked = reject_suspended_participant(request, user, next_url=topic.get_absolute_url())
        if blocked:
            return blocked
        form = PostForm(request.POST)
        if form.is_valid():
            post = Post.objects.create(
                topic=topic, author=user, content=form.cleaned_data["content"]
            )
            from apps.badges.services import record_forum_post

            record_forum_post(user, post_id=post.pk)
            return redirect(topic.get_absolute_url())
    else:
        form = PostForm()
    return render(
        request,
        "forum/topic_detail.html",
        {
            "topic": topic,
            "posts": posts,
            "form": form,
            "forum_user": user,
            "forum_token": token,
            "is_forum_moderator": bool(user.is_forum_moderator or user.is_staff),
            "forum_suspended": not can_participate,
        },
    )


@require_POST
def moderate_delete_post(request, pk):
    """Moderators remove a post and notify the author about a Terms violation."""
    from apps.authentication.connections import create_notification
    from apps.authentication.models import Notification

    moderator, _token = get_or_create_forum_user(request)
    if not moderator.is_forum_moderator:
        messages.error(request, "Only forum moderators can remove posts.")
        return redirect("forum:index")

    post = get_object_or_404(Post.objects.select_related("topic", "author"), pk=pk)
    topic = post.topic
    author = post.author
    topic_title = topic.title
    post.delete()

    if author.pk != moderator.pk:
        create_notification(
            recipient=author,
            actor=moderator,
            notification_type=Notification.TYPE_FORUM_VIOLATION,
            message=(
                f'A forum moderator removed your post in "{topic_title}" because it '
                "violated the Code of Conduct. Please keep discussions civil and "
                "supportive of fellow learners."
            ),
        )
        messages.success(
            request,
            "Post removed and the author was notified about the Code of Conduct violation.",
        )
    else:
        messages.success(request, "Post removed.")
    return redirect(topic.get_absolute_url())


@require_POST
def toggle_post_like(request, pk):
    """Toggle a like on a forum post (like only — no dislike)."""
    user, _token = get_or_create_forum_user(request)
    post = get_object_or_404(Post.objects.select_related("topic"), pk=pk)
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    if not forum_participation_allowed(user):
        if wants_json:
            return JsonResponse(
                {"success": False, "error": "Forum access is suspended.", "post_id": post.pk},
                status=403,
            )
        blocked = reject_suspended_participant(request, user, next_url=post.topic.get_absolute_url())
        return blocked
    like = PostLike.objects.filter(post=post, user=user).first()
    if like:
        like.delete()
        liked = False
    else:
        PostLike.objects.create(post=post, user=user)
        liked = True
        from apps.badges.services import record_post_like_threshold

        record_post_like_threshold(post, post.likes.count())

    like_count = post.likes.count()
    if wants_json:
        return JsonResponse({"liked": liked, "like_count": like_count, "post_id": post.pk})
    return redirect(post.topic.get_absolute_url())


def code_of_conduct(request):
    """Public Code of Conduct for the forum community."""
    user, token = get_or_create_forum_user(request)
    return render(
        request,
        "forum/code_of_conduct.html",
        {
            "forum_user": user,
            "forum_token": token,
            "forum_suspended": not forum_participation_allowed(user),
        },
    )


@require_http_methods(["GET", "POST"])
def alert_admin(request):
    """Confidential Code of Conduct report — emailed to admins like bug reports."""
    user, token = get_or_create_forum_user(request)
    previous = request.GET.get("from") or request.POST.get("previous_page") or request.META.get("HTTP_REFERER") or ""
    reported_nickname = (request.GET.get("user") or request.POST.get("reported_nickname") or "").strip()

    if request.method == "POST":
        form = ConductReportForm(request.POST)
        if form.is_valid():
            submission = ForumConductReport.objects.create(
                reporter=user,
                message=form.cleaned_data["message"].strip(),
                previous_page=(form.cleaned_data.get("previous_page") or "").strip()[:500],
                reported_nickname=(form.cleaned_data.get("reported_nickname") or "")[:150],
                want_reply=bool(form.cleaned_data.get("want_reply")),
                reply_email=(form.cleaned_data.get("email") or "").strip(),
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
            )
            if _send_conduct_report_email(submission):
                submission.email_sent = True
                submission.save(update_fields=["email_sent"])
            request.session["forum_report_want_reply"] = bool(submission.want_reply)
            return redirect("forum:alert_admin_thanks")
    else:
        form = ConductReportForm(
            initial={
                "previous_page": previous,
                "reported_nickname": reported_nickname,
            }
        )

    return render(
        request,
        "forum/alert_admin.html",
        {
            "form": form,
            "previous_page": form["previous_page"].value() or previous,
            "forum_user": user,
            "forum_token": token,
            "forum_suspended": not forum_participation_allowed(user),
        },
    )


def alert_admin_thanks(request):
    want_reply = bool(request.session.pop("forum_report_want_reply", False))
    return render(
        request,
        "forum/alert_admin_thanks.html",
        {"want_reply": want_reply},
    )


def _feedback_recipient() -> str:
    explicit = getattr(settings, "FEEDBACK_TO_EMAIL", None) or ""
    if explicit:
        return explicit
    admins = getattr(settings, "ADMINS", None) or []
    if admins:
        return admins[0][1]
    return getattr(settings, "DEFAULT_FROM_EMAIL", None) or "admin@localhost"


def _send_conduct_report_email(submission: ForumConductReport) -> bool:
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
    to_email = _feedback_recipient()
    reporter_name = (
        submission.reporter.get_display_name()
        if submission.reporter_id and hasattr(submission.reporter, "get_display_name")
        else "(unknown)"
    )
    reporter_token = getattr(submission.reporter, "token", None) or ""
    subject = "Forum Code of Conduct report"
    if submission.want_reply:
        subject += " (reply requested)"

    body_lines = [
        "New confidential forum conduct report:",
        "",
        f"Report id: {submission.pk}",
        f"Reporter: {reporter_name}",
        f"Reporter token hint: {reporter_token[:8] + '...' if reporter_token else '(none)'}",
        f"Reported nickname: {submission.reported_nickname or '(not provided)'}",
        f"Previous page: {submission.previous_page or '(not provided)'}",
        f"Reply requested: {'yes' if submission.want_reply else 'no'}",
        f"Reply email: {submission.reply_email or '(none)'}",
        f"User agent: {submission.user_agent}",
        "",
        "Message:",
        submission.message,
        "",
        "Also saved under Forum → Forum conduct reports.",
        "To suspend forum access (exercises remain available), open the user in Admin",
        "and set Forum suspension, or use Suspend forum on their public profile.",
    ]
    mail = EmailMessage(
        subject=subject,
        body="\n".join(body_lines),
        from_email=from_email,
        to=[to_email],
    )
    if submission.want_reply and submission.reply_email:
        mail.reply_to = [submission.reply_email]
    try:
        mail.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to email forum conduct report %s", submission.pk)
        return False


@require_POST
def suspend_forum_user(request, nickname):
    """Moderators/staff suspend a member from forum participation only."""
    moderator, _token = get_or_create_forum_user(request)
    if not (moderator.is_forum_moderator or moderator.is_staff):
        messages.error(request, "Only forum moderators can suspend members.")
        return redirect("forum:index")

    profile = get_object_or_404(UserProfile.objects.select_related("user"), nickname__iexact=nickname)
    target = profile.user
    if target.pk == moderator.pk:
        messages.error(request, "You cannot suspend yourself.")
        return redirect(profile.get_absolute_url())
    if target.is_forum_moderator or target.is_staff:
        messages.error(request, "You cannot suspend another moderator or staff member.")
        return redirect(profile.get_absolute_url())

    days_raw = (request.POST.get("days") or "").strip()
    days = int(days_raw) if days_raw.isdigit() and int(days_raw) > 0 else None
    note = (request.POST.get("note") or "").strip()[:500]
    set_forum_suspension(target, moderator=moderator, days=days, note=note)
    messages.success(
        request,
        f"{profile.nickname}'s forum access was suspended. They can still use exercises.",
    )
    return redirect(profile.get_absolute_url())


@require_POST
def unsuspend_forum_user(request, nickname):
    """Moderators/staff restore forum participation."""
    moderator, _token = get_or_create_forum_user(request)
    if not (moderator.is_forum_moderator or moderator.is_staff):
        messages.error(request, "Only forum moderators can restore forum access.")
        return redirect("forum:index")

    profile = get_object_or_404(UserProfile.objects.select_related("user"), nickname__iexact=nickname)
    clear_forum_suspension(profile.user, moderator=moderator)
    messages.success(request, f"{profile.nickname}'s forum access was restored.")
    return redirect(profile.get_absolute_url())


def download_token(request):
    """Download an identification-token passkey file (progress is tracked server-side)."""
    user, token = get_or_create_forum_user(request)
    display_name = user.get_display_name() if hasattr(user, "get_display_name") else (user.username or "")

    include_full_token = request.GET.get("include_raw_token", "").lower() in {"1", "true", "yes"}
    data = {
        "version": 1,
        "forum_token": token if include_full_token else None,
        "username": display_name,
        "token_hint": "This file is your identification token. Exercise progress is saved with your account.",
    }

    content = json.dumps(data, indent=2)
    response = HttpResponse(content, content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="django_platform_passkey_{token[:8]}.json"'
    return response


def _safe_next_url(request, candidate: str | None) -> str:
    """Allow only relative same-host redirects."""
    fallback = reverse("forum:index")
    url = (candidate or "").strip() or fallback
    if url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return url
    # Also allow plain relative paths without a host.
    if url.startswith("/") and not url.startswith("//"):
        return url
    return fallback


def restore_token(request):
    """Restore a forum identity and exercise progress using a Passkey Bundle JSON file or raw token."""
    next_url = _safe_next_url(
        request,
        request.POST.get("next") or request.GET.get("next"),
    )
    if request.method == "POST":
        extracted_token = None
        exercise_progress = {}

        # Check uploaded file
        token_file = request.FILES.get("token_file")
        if token_file:
            try:
                file_content = token_file.read().decode("utf-8", errors="ignore")
                # Try parsing as unified Passkey JSON
                try:
                    data = json.loads(file_content)
                    if isinstance(data, dict) and "forum_token" in data:
                        extracted_token = data["forum_token"]
                        raw_progress = data.get("exercise_progress", {})
                        exercise_progress = raw_progress if isinstance(raw_progress, dict) else {}
                except json.JSONDecodeError:
                    # Fallback to plain text token lookup
                    match = re.search(r"Token:\s*([a-fA-F0-9]{32})", file_content)
                    if match:
                        extracted_token = match.group(1)
                    else:
                        hex_match = re.search(r"\b([a-fA-F0-9]{32})\b", file_content)
                        if hex_match:
                            extracted_token = hex_match.group(1)
            except Exception:
                pass

        # Check text input if file wasn't provided or didn't match
        if not extracted_token:
            token_input = request.POST.get("token_input", "").strip()
            if token_input:
                match = re.search(r"([a-fA-F0-9]{32})", token_input)
                if match:
                    extracted_token = match.group(1)
                else:
                    extracted_token = token_input

        if extracted_token:
            user = CustomUser.objects.filter(token=extracted_token).first()
            if user and not user.is_active:
                messages.error(
                    request,
                    "This account is scheduled for deletion and can no longer be used.",
                )
                return redirect(next_url)
            if user:
                request.session["forum_token"] = extracted_token
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                return render(
                    request,
                    "forum/restore_success.html",
                    {
                        "progress_data": exercise_progress,
                        "next_url": next_url,
                    },
                )

        messages.error(request, "Invalid identity token. No matching forum user found.")
    return redirect(next_url)


