from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse


def challenge_image_upload_to(instance, filename):
    week = instance.contest.week
    return f"challenges/data_viz/{week.iso_year}/W{week.iso_week:02d}/{filename}"


class ChallengeWeek(models.Model):
    """One ISO calendar week of weekly challenges."""

    iso_year = models.PositiveIntegerField()
    iso_week = models.PositiveIntegerField()
    starts_on = models.DateField()
    ends_on = models.DateField()

    class Meta:
        ordering = ["-iso_year", "-iso_week"]
        constraints = [
            models.UniqueConstraint(
                fields=["iso_year", "iso_week"],
                name="challenges_week_unique_iso",
            )
        ]
        verbose_name = "Challenge Week"
        verbose_name_plural = "Challenge Weeks"

    def __str__(self):
        return f"{self.iso_year}-W{self.iso_week:02d}"

    @property
    def label(self):
        return f"Week {self.iso_week}, {self.iso_year}"

    def get_absolute_url(self):
        return reverse(
            "challenges:weekly",
            kwargs={"iso_year": self.iso_year, "iso_week": self.iso_week},
        )


class Contest(models.Model):
    KIND_DATA_VIZ = "data_viz"
    KIND_RESOURCE = "resource"
    KIND_MISLEADING_HEADLINE = "misleading_headline"
    KIND_CHOICES = [
        (KIND_DATA_VIZ, "Weekly Data Viz"),
        (KIND_RESOURCE, "Resource of the Week"),
        (KIND_MISLEADING_HEADLINE, "Misleading Headline"),
    ]

    week = models.ForeignKey(ChallengeWeek, on_delete=models.CASCADE, related_name="contests")
    kind = models.CharField(max_length=32, choices=KIND_CHOICES)

    class Meta:
        ordering = ["kind"]
        constraints = [
            models.UniqueConstraint(
                fields=["week", "kind"],
                name="challenges_contest_unique_week_kind",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} ({self.week})"

    @property
    def is_data_viz(self):
        return self.kind == self.KIND_DATA_VIZ

    @property
    def is_resource(self):
        return self.kind == self.KIND_RESOURCE

    @property
    def is_misleading_headline(self):
        return self.kind == self.KIND_MISLEADING_HEADLINE


class Submission(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="submissions")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_submissions",
    )
    title = models.CharField(max_length=200)
    notes = models.TextField(blank=True)
    image = models.ImageField(upload_to=challenge_image_upload_to, blank=True, null=True)
    url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} by {self.author}"

    def clean(self):
        if self.contest_id and self.contest.is_data_viz:
            if not self.image:
                raise ValidationError({"image": "A PNG image is required for Data Viz submissions."})
            if self.url:
                raise ValidationError({"url": "Data Viz submissions should not include a link."})
        if self.contest_id and self.contest.is_resource:
            if not self.url:
                raise ValidationError({"url": "A link is required for Resource of the Week submissions."})
            if self.image:
                raise ValidationError({"image": "Resource submissions should not include an image."})
        if self.contest_id and self.contest.is_misleading_headline:
            if not (self.title or "").strip():
                raise ValidationError({"title": "Please provide the misleading headline."})
            if self.image:
                raise ValidationError({"image": "Misleading Headline submissions should not include an image."})

    @property
    def upvote_count(self):
        return self.upvotes.count()


class SubmissionUpvote(models.Model):
    """An upvote on a challenge submission (upvote only — no downvote)."""

    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="upvotes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="challenge_upvotes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["submission", "user"],
                name="challenges_upvote_unique_user",
            )
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Upvote by {self.user} on submission {self.submission_id}"
