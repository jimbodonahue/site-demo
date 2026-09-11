from django.db import migrations


SOFT_SKILL_PROMPTS = {
    "pandas-introduction": (
        "Imagine a teammate who does not write code asks what you learned from this exercise. "
        "In 2–4 sentences, explain one pandas technique you used and why it matters for "
        "understanding a dataset."
    ),
    "fill-missing-values-generated-data": (
        "Filling missing values always involves judgment. Describe how you would explain your "
        "chosen approach to a stakeholder, including one risk or assumption they should know about."
    ),
    "clean-messy-dataset": (
        "Data quality work often happens before analysis begins. Write a short note you could send "
        "to a colleague summarizing what was wrong with the data and why cleaning it first improves "
        "trust in the results."
    ),
}


def seed_soft_skill_prompts(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    for slug, prompt in SOFT_SKILL_PROMPTS.items():
        Exercise.objects.filter(slug=slug).update(soft_skill_prompt=prompt)


def clear_soft_skill_prompts(apps, schema_editor):
    Exercise = apps.get_model("exercises", "Exercise")
    Exercise.objects.filter(slug__in=SOFT_SKILL_PROMPTS.keys()).update(soft_skill_prompt="")


class Migration(migrations.Migration):

    dependencies = [
        ("exercises", "0006_soft_skill_and_post_likes"),
    ]

    operations = [
        migrations.RunPython(seed_soft_skill_prompts, clear_soft_skill_prompts),
    ]
