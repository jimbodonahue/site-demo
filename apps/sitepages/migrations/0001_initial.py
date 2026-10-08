from django.db import migrations, models
import django.utils.timezone


def seed_welcome_news(apps, schema_editor):
	NewsUpdate = apps.get_model("sitepages", "NewsUpdate")
	if NewsUpdate.objects.exists():
		return
	NewsUpdate.objects.create(
		title="Welcome to Jim's Data Gym",
		body=(
			"The gym is open. Start with How to Gym for a quick tour, then pick a track "
			"and practice at your own pace. More news from Jim will show up here."
		),
		is_published=True,
	)


def unseed_welcome_news(apps, schema_editor):
	NewsUpdate = apps.get_model("sitepages", "NewsUpdate")
	NewsUpdate.objects.filter(title="Welcome to Jim's Data Gym").delete()


class Migration(migrations.Migration):
	initial = True

	dependencies = []

	operations = [
		migrations.CreateModel(
			name="NewsUpdate",
			fields=[
				("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
				("title", models.CharField(max_length=200)),
				("body", models.TextField(help_text="Plain text or light Markdown-style notes.")),
				("published_at", models.DateTimeField(default=django.utils.timezone.now)),
				("is_published", models.BooleanField(default=True)),
				("created_at", models.DateTimeField(auto_now_add=True)),
				("updated_at", models.DateTimeField(auto_now=True)),
			],
			options={
				"verbose_name": "news update",
				"verbose_name_plural": "news updates",
				"ordering": ["-published_at", "-created_at"],
			},
		),
		migrations.RunPython(seed_welcome_news, unseed_welcome_news),
	]
