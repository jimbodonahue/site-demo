from django.core.management.base import BaseCommand

from apps.exercises.content import sync_exercise_from_content
from apps.exercises.models import Exercise


class Command(BaseCommand):
	help = (
		"Sync Exercise DB fields (intro, soft skill, graphic, starter, messages) "
		"from apps/exercises/content/exercises/<slug>/."
	)

	def add_arguments(self, parser):
		parser.add_argument(
			"--slug",
			action="append",
			dest="slugs",
			help="Limit to one or more exercise slugs (repeatable).",
		)
		parser.add_argument(
			"--dry-run",
			action="store_true",
			help="Show which fields would change without saving.",
		)

	def handle(self, *args, **options):
		queryset = Exercise.objects.all().order_by("order", "title")
		slugs = options.get("slugs") or []
		if slugs:
			queryset = queryset.filter(slug__in=slugs)
		dry_run = bool(options.get("dry_run"))
		updated = 0
		for exercise in queryset:
			fields = sync_exercise_from_content(exercise)
			if not fields:
				continue
			updated += 1
			label = ", ".join(fields)
			if dry_run:
				self.stdout.write(f"would update {exercise.slug}: {label}")
				continue
			exercise.save(update_fields=[*fields, "updated_at"])
			self.stdout.write(self.style.SUCCESS(f"updated {exercise.slug}: {label}"))
		if updated == 0:
			self.stdout.write("No content-file changes to apply.")
		elif dry_run:
			self.stdout.write(f"{updated} exercise(s) would be updated.")
		else:
			self.stdout.write(self.style.SUCCESS(f"Synced {updated} exercise(s)."))
