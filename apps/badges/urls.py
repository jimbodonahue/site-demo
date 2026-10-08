from django.urls import path

from . import views

app_name = "badges"

urlpatterns = [
    path("", views.badge_gallery, name="index"),
]
