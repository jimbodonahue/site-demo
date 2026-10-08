from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, list_zoo_datasets
from apps.forum.views import get_or_create_forum_user
from project_core.ratelimit import check_rate_limit

from .deletion import maybe_process_due_account_deletions, schedule_account_deletion
from .forms import AccountDeletionForm, EmailPasskeyForm, UserOnboardingForm, UserProfileForm
from .models import AccountDeletionRequest, UserProfile


def _ensure_membership_user(request):
    """Ensure the visitor has a passkey identity and profile shell."""
    maybe_process_due_account_deletions()
    user, token = get_or_create_forum_user(request)
    profile_obj = getattr(user, "profile", None)
    if profile_obj is None:
        profile_obj = UserProfile(user=user, nickname=f"user-{user.pk}")
        profile_obj.save()
    elif not profile_obj.pk:
        profile_obj.save()
    return user, token, profile_obj


def profile(request):
    user, token, profile_obj = _ensure_membership_user(request)
    pending_deletion = AccountDeletionRequest.objects.filter(
        user=user,
        status=AccountDeletionRequest.STATUS_PENDING,
    ).first()

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile_obj)
        email_form = EmailPasskeyForm()
        if form.is_valid():
            profile_obj = form.save(commit=False)
            profile_obj.user = user
            profile_obj.save()
            messages.success(request, "Your account details have been saved.")
            return redirect("membership")
    else:
        form = UserProfileForm(instance=profile_obj)
        email_form = EmailPasskeyForm()

    from apps.badges.services import earned_badges_for_profile

    return render(
        request,
        "authentication/profile.html",
        {
            "form": form,
            "email_form": email_form,
            "profile": profile_obj,
            "passkey": token,
            "pending_deletion": pending_deletion,
            "can_delete_account": not (user.is_staff or user.is_superuser),
            "earned_badges": earned_badges_for_profile(user),
        },
    )


@require_http_methods(["GET", "POST"])
def delete_account(request):
    """Request account deletion with confirmation; data removed within 48 hours."""
    user, token, profile_obj = _ensure_membership_user(request)

    if user.is_staff or user.is_superuser:
        messages.error(request, "Staff accounts cannot be deleted from this page.")
        return redirect("membership")

    pending = AccountDeletionRequest.objects.filter(
        user=user,
        status=AccountDeletionRequest.STATUS_PENDING,
    ).first()
    if pending:
        return render(
            request,
            "authentication/delete_account_scheduled.html",
            {"deletion_request": pending},
        )

    if request.method == "POST":
        form = AccountDeletionForm(request.POST)
        if form.is_valid():
            deletion = schedule_account_deletion(
                user,
                reason=form.cleaned_data["reason"],
                details=form.cleaned_data.get("details") or "",
                feedback=form.cleaned_data.get("feedback") or "",
                user_agent=request.META.get("HTTP_USER_AGENT") or "",
            )
            logout(request)
            request.session.flush()
            return render(
                request,
                "authentication/delete_account_scheduled.html",
                {"deletion_request": deletion, "just_submitted": True},
            )
    else:
        form = AccountDeletionForm()

    return render(
        request,
        "authentication/delete_account.html",
        {
            "form": form,
            "profile": profile_obj,
            "passkey": token,
        },
    )


@require_POST
def email_passkey(request):
    user, token, profile_obj = _ensure_membership_user(request)
    form = EmailPasskeyForm(request.POST)

    if not token:
        messages.error(request, "No passkey is available for this membership.")
        return redirect("membership")

    # The passkey is a bearer credential, so sending it is throttled per IP.
    allowed, _retry = check_rate_limit(
        request,
        action="passkey_email",
        limit=getattr(settings, "PASSKEY_EMAIL_RATE_LIMIT", 3),
        window_seconds=getattr(settings, "PASSKEY_EMAIL_RATE_WINDOW", 900),
        by_ip_only=True,
    )
    if not allowed:
        messages.error(request, "Too many passkey emails requested. Please try again later.")
        return redirect("membership")

    if form.is_valid():
        recipient = form.cleaned_data["email"]
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
        subject = "Your membership passkey"
        body = (
            "Here is your membership passkey. Store it somewhere safe and do not share it.\n"
            "Anyone with this passkey can use your identity on this site.\n"
            "Important: your passkey cannot be replaced if it is lost. There is no password reset.\n"
            "If you lose it, you would have to create a new account and start over — "
            "previous progress and posts cannot be recovered.\n\n"
            f"Passkey:\n{token}\n\n"
            "This email address was not saved. We only used it to send this message.\n"
        )
        send_mail(subject, body, from_email, [recipient], fail_silently=False)
        messages.success(
            request,
            "Your passkey was emailed. That address was not stored on your account.",
        )
        return redirect("membership")

    from apps.badges.services import earned_badges_for_profile

    profile_form = UserProfileForm(instance=profile_obj)
    pending_deletion = AccountDeletionRequest.objects.filter(
        user=user,
        status=AccountDeletionRequest.STATUS_PENDING,
    ).first()
    return render(
        request,
        "authentication/profile.html",
        {
            "form": profile_form,
            "email_form": form,
            "profile": profile_obj,
            "passkey": token,
            "pending_deletion": pending_deletion,
            "can_delete_account": not (user.is_staff or user.is_superuser),
            "earned_badges": earned_badges_for_profile(user),
        },
    )


def onboarding(request):
    if not request.user.is_authenticated:
        return redirect("home")

    profile_obj = getattr(request.user, "profile", None)
    if profile_obj is None:
        profile_obj = UserProfile(user=request.user, nickname=f"user-{request.user.pk or 'new'}")

    if request.method == "POST":
        form = UserOnboardingForm(request.POST)
        if form.is_valid():
            if not profile_obj.pk:
                profile_obj.save()
            profile_obj.set_ranked_topics(form.cleaned_data["preferred_topics"])
            profile_obj.dataset_file = form.cleaned_data.get("dataset_file") or ""
            profile_obj.onboarding_complete = True
            profile_obj.save()
            messages.success(request, "Your topic preferences have been saved.")
            return redirect("home")
    else:
        ranked = profile_obj.ranked_topics() if profile_obj.pk else []
        if not ranked and profile_obj.data_field:
            ranked = [profile_obj.data_field]
        initial = {
            "topic_1": (ranked[0] if len(ranked) > 0 else "healthcare"),
            "topic_2": (ranked[1] if len(ranked) > 1 else ""),
            "topic_3": (ranked[2] if len(ranked) > 2 else ""),
            "topic_4": (ranked[3] if len(ranked) > 3 else ""),
            "topic_5": (ranked[4] if len(ranked) > 4 else ""),
            "dataset_file": profile_obj.dataset_file or "",
        }
        form = UserOnboardingForm(initial=initial)

    dataset_map = {sector: [path.name for path in list_zoo_datasets(sector)] for sector in DATA_SCIENCE_SECTORS}
    return render(
        request,
        "authentication/onboarding.html",
        {"form": form, "profile": profile_obj, "dataset_map": dataset_map},
    )


def custom_login(request):
    if request.method == "POST":
        allowed, _retry = check_rate_limit(
            request,
            action="login",
            limit=getattr(settings, "LOGIN_RATE_LIMIT", 10),
            window_seconds=getattr(settings, "LOGIN_RATE_WINDOW", 300),
            by_ip_only=True,
        )
        if not allowed:
            messages.error(request, "Too many sign-in attempts. Please wait a few minutes and try again.")
            return render(request, "authentication/login.html", {"form": AuthenticationForm(request)})
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            profile_obj = getattr(user, "profile", None)
            if not profile_obj or not profile_obj.onboarding_complete:
                return redirect("onboarding")
            return redirect("home")
    else:
        form = AuthenticationForm(request)
    return render(request, "authentication/login.html", {"form": form})
