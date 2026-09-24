from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import redirect, render

from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS, list_zoo_datasets

from .forms import UserOnboardingForm, UserProfileForm
from .models import UserProfile


def profile(request):
    if not request.user.is_authenticated:
        return redirect("home")

    profile_obj = getattr(request.user, "profile", None)
    if profile_obj is None:
        profile_obj = UserProfile(user=request.user)

    if request.method == "POST":
        form = UserProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            profile_obj = form.save(commit=False)
            profile_obj.user = request.user
            profile_obj.save()
            messages.success(request, "Your profile has been saved.")
            return redirect("profile")
    else:
        form = UserProfileForm(instance=profile_obj)

    return render(request, "authentication/profile.html", {"form": form, "profile": profile_obj})


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
            profile_obj.data_field = form.cleaned_data["data_field"]
            profile_obj.dataset_file = form.cleaned_data["dataset_file"]
            profile_obj.set_ranked_topics([form.cleaned_data["data_field"]])
            profile_obj.onboarding_complete = True
            profile_obj.save()
            messages.success(request, "Your exercise preferences have been saved.")
            return redirect("home")
    else:
        form = UserOnboardingForm(
            initial={
                "data_field": profile_obj.data_field or "healthcare",
                "dataset_file": profile_obj.dataset_file or "",
            }
        )

    dataset_map = {sector: [path.name for path in list_zoo_datasets(sector)] for sector in DATA_SCIENCE_SECTORS}
    return render(
        request,
        "authentication/onboarding.html",
        {"form": form, "profile": profile_obj, "dataset_map": dataset_map},
    )


def custom_login(request):
    if request.method == "POST":
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
