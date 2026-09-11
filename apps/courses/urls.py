from django.http import HttpResponseGone
from django.urls import path

app_name = "courses"

# Public courses URLs removed; keep a minimal conf so reverse lookups fail cleanly if referenced.


urlpatterns = [
    path("", lambda request: HttpResponseGone("Courses have been replaced by learning tracks."), name="list"),
]
