from django.urls import path

from . import views

app_name = "challenges"

urlpatterns = [
    path("", views.weekly_challenges, name="index"),
    path(
        "<int:iso_year>/W<int:iso_week>/",
        views.weekly_challenges,
        name="weekly",
    ),
    path("submissions/<int:pk>/upvote/", views.toggle_upvote, name="toggle_upvote"),
]
