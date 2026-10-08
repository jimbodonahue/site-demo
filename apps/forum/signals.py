from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.exercises.models import Exercise
from .models import Topic
from .utils import get_system_user


@receiver(post_save, sender=Exercise)
def auto_create_exercise_topic(sender, instance, created, **kwargs):
    """
    Automatically creates a forum discussion topic whenever a published Exercise is created or updated.
    """
    if instance.published:
        system_user = get_system_user()
        Topic.objects.get_or_create(
            exercise=instance,
            defaults={
                "title": f"Discussion: {instance.title}",
                "created_by": system_user,
                "section": Topic.SECTION_EXERCISE,
            },
        )
