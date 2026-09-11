from django.urls import path

from . import views

urlpatterns = [
    path("profile/", views.profile, name="profile"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("login/", views.custom_login, name="login"),
]
