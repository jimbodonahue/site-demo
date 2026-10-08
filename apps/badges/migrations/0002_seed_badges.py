from django.db import migrations

from apps.badges.catalog import BADGE_DEFINITIONS


def seed_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    for definition in BADGE_DEFINITIONS:
        Badge.objects.update_or_create(
            slug=definition["slug"],
            defaults={
                "name": definition["name"],
                "description": definition["description"],
                "category": definition["category"],
                "icon": definition["icon"],
                "threshold": definition["threshold"],
                "sort_order": definition["sort_order"],
                "is_active": True,
            },
        )


def unseed_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    Badge.objects.filter(slug__in=[item["slug"] for item in BADGE_DEFINITIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_badges, unseed_badges),
    ]
