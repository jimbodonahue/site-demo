from django.urls import path
from django.views.generic import TemplateView
from .views import (
    DataZooView,
    ExerciseDetailView,
    TrackDetailView,
    TrackListView,
    repeat_exercise,
    reset_exercise,
    run_exercise,
    run_zoo_explore,
    submit_soft_skill,
    zoo_catalog,
)

app_name = "exercises"

urlpatterns = [
    path("", TrackListView.as_view(), name="list"),
    path("tracks/<slug:slug>/", TrackDetailView.as_view(), name="track_detail"),
    path("zoo/", DataZooView.as_view(), name="zoo"),
    path("zoo/catalog/", zoo_catalog, name="zoo_catalog"),
    path("zoo/run/", run_zoo_explore, name="zoo_run"),
    path(
        "cardio/",
        TemplateView.as_view(template_name="exercises/cardio_placeholder.html"),
        name="cardio",
    ),
    path("<slug:slug>/", ExerciseDetailView.as_view(), name="detail"),
    path("<slug:slug>/run/", run_exercise, name="run"),
    path("<slug:slug>/reset/", reset_exercise, name="reset"),
    path("<slug:slug>/repeat/", repeat_exercise, name="repeat"),
    path("<slug:slug>/soft-skill/", submit_soft_skill, name="soft_skill"),
]
