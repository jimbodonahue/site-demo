from django.urls import path

from .views import (
    ExerciseDetailView,
    TrackDetailView,
    TrackListView,
    repeat_exercise,
    reset_exercise,
    run_exercise,
    submit_soft_skill,
)

app_name = "exercises"

urlpatterns = [
    path("", TrackListView.as_view(), name="list"),
    path("tracks/<slug:slug>/", TrackDetailView.as_view(), name="track_detail"),
    path("<slug:slug>/", ExerciseDetailView.as_view(), name="detail"),
    path("<slug:slug>/run/", run_exercise, name="run"),
    path("<slug:slug>/reset/", reset_exercise, name="reset"),
    path("<slug:slug>/repeat/", repeat_exercise, name="repeat"),
    path("<slug:slug>/soft-skill/", submit_soft_skill, name="soft_skill"),
]
