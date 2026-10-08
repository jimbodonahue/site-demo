from django.contrib import messages
from django.db.models import Count, Exists, OuterRef
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.forum.views import get_or_create_forum_user

from .forms import build_submission_form
from .models import Contest, Submission, SubmissionUpvote
from .utils import ensure_current_week, ensure_week, iso_week_for, recent_weeks


def _annotated_submissions(contest, user):
    liked = SubmissionUpvote.objects.filter(submission_id=OuterRef("pk"), user=user)
    return (
        contest.submissions.select_related("author", "author__profile")
        .annotate(
            annotated_upvote_count=Count("upvotes", distinct=True),
            user_has_upvoted=Exists(liked),
        )
        .order_by("-annotated_upvote_count", "-created_at")
    )


def _week_page_context(request, week, forum_user, forum_token):
    contests = {contest.kind: contest for contest in week.contests.all()}
    data_viz = contests.get(Contest.KIND_DATA_VIZ)
    resource = contests.get(Contest.KIND_RESOURCE)
    misleading = contests.get(Contest.KIND_MISLEADING_HEADLINE)
    current_year, current_week = iso_week_for()
    is_current = week.iso_year == current_year and week.iso_week == current_week

    return {
        "week": week,
        "weeks": recent_weeks(),
        "is_current_week": is_current,
        "data_viz_contest": data_viz,
        "resource_contest": resource,
        "misleading_contest": misleading,
        "data_viz_submissions": _annotated_submissions(data_viz, forum_user) if data_viz else [],
        "resource_submissions": _annotated_submissions(resource, forum_user) if resource else [],
        "misleading_submissions": _annotated_submissions(misleading, forum_user) if misleading else [],
        "data_viz_form": build_submission_form(data_viz) if data_viz and is_current else None,
        "resource_form": build_submission_form(resource) if resource and is_current else None,
        "misleading_form": build_submission_form(misleading) if misleading and is_current else None,
        "forum_user": forum_user,
        "forum_token": forum_token,
    }


def weekly_challenges(request, iso_year=None, iso_week=None):
    """Show weekly contests for the selected (or current) week."""
    forum_user, forum_token = get_or_create_forum_user(request)
    if iso_year is None or iso_week is None:
        week = ensure_current_week()
    else:
        week = ensure_week(iso_year, iso_week)

    if request.method == "POST":
        current_year, current_week_num = iso_week_for()
        if week.iso_year != current_year or week.iso_week != current_week_num:
            messages.error(request, "Submissions are only open for the current week.")
            return redirect(week.get_absolute_url())

        contest_id = request.POST.get("contest_id")
        contest = get_object_or_404(Contest, pk=contest_id, week=week)
        form = build_submission_form(contest, data=request.POST, files=request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.contest = contest
            submission.author = forum_user
            submission.full_clean()
            submission.save()
            messages.success(request, "Your suggestion was submitted. Good luck!")
            return redirect(week.get_absolute_url() + f"#contest-{contest.kind}")

        context = _week_page_context(request, week, forum_user, forum_token)
        if contest.is_data_viz:
            context["data_viz_form"] = form
        elif contest.is_misleading_headline:
            context["misleading_form"] = form
        else:
            context["resource_form"] = form
        messages.error(request, "Please fix the errors in your submission.")
        return render(request, "challenges/weekly.html", context)

    return render(
        request,
        "challenges/weekly.html",
        _week_page_context(request, week, forum_user, forum_token),
    )


@require_POST
def toggle_upvote(request, pk):
    """Toggle an upvote on a challenge submission."""
    user, _token = get_or_create_forum_user(request)
    submission = get_object_or_404(Submission.objects.select_related("contest__week"), pk=pk)
    upvote = SubmissionUpvote.objects.filter(submission=submission, user=user).first()
    if upvote:
        upvote.delete()
        upvoted = False
    else:
        SubmissionUpvote.objects.create(submission=submission, user=user)
        upvoted = True

    upvote_count = submission.upvotes.count()
    wants_json = (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )
    if wants_json:
        return JsonResponse(
            {"upvoted": upvoted, "upvote_count": upvote_count, "submission_id": submission.pk}
        )
    return redirect(submission.contest.week.get_absolute_url() + f"#submission-{submission.pk}")
