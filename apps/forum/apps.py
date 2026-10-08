from django.apps import AppConfig


class ForumConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.forum"
    verbose_name = "Discussion Forum"

    def ready(self):
        import apps.forum.signals  # noqa

