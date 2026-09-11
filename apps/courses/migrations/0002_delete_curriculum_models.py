from django.db import migrations


class Migration(migrations.Migration):
    """Remove curriculum models now that exercises use tracks."""

    dependencies = [
        ("courses", "0001_initial"),
        ("exercises", "0012_remove_course_lesson_fields"),
    ]

    operations = [
        migrations.DeleteModel(name="Lesson"),
        migrations.DeleteModel(name="Module"),
        migrations.DeleteModel(name="Course"),
    ]
