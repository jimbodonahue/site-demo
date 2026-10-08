from django.urls import path

from . import social_views, views

urlpatterns = [
    path("membership/", views.profile, name="membership"),
    path("membership/email-passkey/", views.email_passkey, name="email_passkey"),
    path("membership/delete/", views.delete_account, name="delete_account"),
    path("profile/", views.profile, name="profile"),
    path("onboarding/", views.onboarding, name="onboarding"),
    path("login/", views.custom_login, name="login"),
    path("notifications/", social_views.notifications, name="notifications"),
    path(
        "notifications/<int:notification_id>/respond/",
        social_views.respond_connection,
        name="respond_connection",
    ),
    path(
        "notifications/<int:notification_id>/reveal-contact/",
        social_views.reveal_contact,
        name="reveal_contact",
    ),
    path("u/<str:nickname>/", social_views.public_profile, name="public_profile"),
    path("u/<str:nickname>/connect/", social_views.request_connection, name="request_connection"),
    path("u/<str:nickname>/share-contact/", social_views.share_contact, name="share_contact"),
    path("u/<str:nickname>/block/", social_views.block_user, name="block_user"),
    path("u/<str:nickname>/unblock/", social_views.unblock_user, name="unblock_user"),
]
