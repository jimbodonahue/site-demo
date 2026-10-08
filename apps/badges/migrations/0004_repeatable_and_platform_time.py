from django.db import migrations, models

from apps.badges.catalog import BADGE_DEFINITIONS


NEW_BADGE_SLUGS = {"exercise-complete", "ten-hours"}


def seed_new_badges(apps, schema_editor):
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
                "is_repeatable": bool(definition.get("is_repeatable", False)),
            },
        )


def unseed_new_badges(apps, schema_editor):
    Badge = apps.get_model("badges", "Badge")
    Badge.objects.filter(slug__in=NEW_BADGE_SLUGS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0003_plot_bonus_counters"),
    ]

    operations = [
        migrations.AddField(
            model_name="badge",
            name="is_repeatable",
            field=models.BooleanField(
                default=False,
                help_text="When true, this badge can be earned multiple times (e.g. every exercise completion).",
            ),
        ),
        migrations.AddField(
            model_name="userbadgestats",
            name="platform_seconds",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Accumulated active time on the platform while signed in.",
            ),
        ),
        migrations.AddField(
            model_name="userbadgestats",
            name="last_seen_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Last authenticated presence timestamp used for time accumulation.",
                null=True,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="userbadge",
            name="badges_userbadge_unique_user_badge",
        ),
        migrations.AddIndex(
            model_name="userbadge",
            index=models.Index(fields=["user", "badge"], name="badges_userbadge_user_badge_idx"),
        ),
        migrations.RunPython(seed_new_badges, unseed_new_badges),
    ]
