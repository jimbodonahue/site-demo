"""Disable ML track on size-capped hosts (no scikit-learn / xgboost in requirements)."""

from django.db import migrations

ML_SLUGS = (
	"ml-data-preparation",
	"ml-regression-strategies",
	"ml-intro-classification",
	"ml-advanced-classification",
	"ml-ensemble-methods",
	"ml-unsupervised-learning",
)


def disable_ml(apps, schema_editor):
	Exercise = apps.get_model("exercises", "Exercise")
	Track = apps.get_model("exercises", "Track")

	Exercise.objects.filter(slug__in=ML_SLUGS).update(
		published=False,
		is_placeholder=True,
	)
	Track.objects.filter(slug="machine-learning-and-ai").update(
		published=True,
		is_placeholder=True,
		summary=(
			"Coming soon on this host: supervised learning, model evaluation, and applied AI. "
			"The full site installs scikit-learn / xgboost; this lite deploy omits them for disk quota."
		),
	)


def noop_reverse(apps, schema_editor):
	pass


class Migration(migrations.Migration):

	dependencies = [
		("exercises", "0024_attempt_history"),
	]

	operations = [
		migrations.RunPython(disable_ml, noop_reverse),
	]
