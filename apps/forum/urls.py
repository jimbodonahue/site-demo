from django.urls import path

from . import views

app_name = "forum"

urlpatterns = [
    path("", views.topic_list, name="index"),
    path("topics/", views.topic_list, name="topic_list"),
    path("create/", views.topic_create, name="topic_create"),
    path("code-of-conduct/", views.code_of_conduct, name="code_of_conduct"),
    path("alert-admin/", views.alert_admin, name="alert_admin"),
    path("alert-admin/thanks/", views.alert_admin_thanks, name="alert_admin_thanks"),
    path("u/<str:nickname>/suspend/", views.suspend_forum_user, name="suspend_user"),
    path("u/<str:nickname>/unsuspend/", views.unsuspend_forum_user, name="unsuspend_user"),
    path("<int:pk>/", views.topic_detail, name="topic_detail"),
    path("posts/<int:pk>/like/", views.toggle_post_like, name="toggle_like"),
    path("posts/<int:pk>/moderate-delete/", views.moderate_delete_post, name="moderate_delete_post"),
    path("exercise/<slug:exercise_slug>/create/", views.exercise_topic_create, name="exercise_topic_create"),
    path("token/download/", views.download_token, name="download_token"),
    path("token/restore/", views.restore_token, name="restore_token"),
]

