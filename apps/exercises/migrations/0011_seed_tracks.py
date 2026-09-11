from django.db import migrations


TRACK_EXERCISE_ORDER = {
    "pandas-introduction": 10,
    "fill-missing-values-generated-data": 20,
    "clean-messy-dataset": 30,
}


def seed_tracks(apps, schema_editor):
    Track = apps.get_model("exercises", "Track")
    Exercise = apps.get_model("exercises", "Exercise")

    analytics, _ = Track.objects.update_or_create(
        slug="data-analytics-with-python",
        defaults={
            "title": "Data Analytics with Python",
            "summary": (
                "Build practical data analysis skills with pandas and Python: "
                "explore tabular data, handle missing values, and clean real-world datasets."
            ),
            "order": 10,
            "published": True,
            "is_placeholder": False,
        },
    )
    Track.objects.update_or_create(
        slug="machine-learning-and-ai",
        defaults={
            "title": "Machine Learning and AI",
            "summary": (
                "Coming soon: supervised learning, model evaluation, and applied AI workflows. "
                "Exercises for this track are on the way."
            ),
            "order": 20,
            "published": True,
            "is_placeholder": True,
        },
    )

    for slug, order in TRACK_EXERCISE_ORDER.items():
        Exercise.objects.filter(slug=slug).update(track=analytics, order=order)


def unseed_tracks(apps, schema_editor):
    Track = apps.get_model("exercises", "Track")
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(track__slug="data-analytics-with-python").update(track=None)
    Track.objects.filter(
        slug__in=["data-analytics-with-python", "machine-learning-and-ai"]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("exercises", "0010_track_model"),
    ]

    operations = [
        migrations.RunPython(seed_tracks, unseed_tracks),
    ]
