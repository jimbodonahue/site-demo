from django.urls import path

from . import views

urlpatterns = [
	path("", views.LandingView.as_view(), name="home"),
	path("welcome/", views.site_gate, name="site_gate"),
	path("about/", views.AboutGymView.as_view(), name="about"),
	path("about/trainers/", views.TrainersView.as_view(), name="about_trainers"),
	path("how-to-gym/", views.HowToGymView.as_view(), name="how_to_gym"),
	path("feedback/", views.feedback, name="feedback"),
	path("feedback/thanks/", views.feedback_thanks, name="feedback_thanks"),
]
