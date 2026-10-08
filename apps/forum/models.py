from django.db import models
from django.conf import settings
from django.urls import reverse

from apps.forum.rendering import render_forum_markdown_html


class Topic(models.Model):
    """A discussion thread. May be linked to an Exercise for per‑exercise forums."""

    SECTION_EXERCISE = "exercise"
    SECTION_RESOURCES = "resources"
    SECTION_JOB_MARKET = "job_market"
    SECTION_ACHIEVEMENTS = "achievements"
    SECTION_GENERAL = "general"

    SECTION_CHOICES = [
        (SECTION_EXERCISE, "Exercise Discussions"),
        (SECTION_RESOURCES, "Useful Resources"),
        (SECTION_JOB_MARKET, "Job Market Readiness"),
        (SECTION_ACHIEVEMENTS, "Celebrate Achievements"),
        (SECTION_GENERAL, "Other Discussions"),
    ]

    title = models.CharField(max_length=200)
    section = models.CharField(
        max_length=32,
        choices=SECTION_CHOICES,
        default=SECTION_GENERAL,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forum_topics"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Optional link to an Exercise; null for generic topics
    exercise = models.ForeignKey(
        "exercises.Exercise",
        on_delete=models.CASCADE,
        related_name="forum_topics",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Forum Topic"
        verbose_name_plural = "Forum Topics"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("forum:topic_detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if self.exercise_id and self.section != self.SECTION_EXERCISE:
            self.section = self.SECTION_EXERCISE
        super().save(*args, **kwargs)


class Post(models.Model):
    """A single message within a Topic."""

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="posts")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forum_posts"
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Forum Post"
        verbose_name_plural = "Forum Posts"

    def __str__(self) -> str:
        return f"Post by {self.author} on {self.topic}"

    def render_content_html(self):
        return render_forum_markdown_html(self.content)

    @property
    def like_count(self) -> int:
        return self.likes.count()


class PostLike(models.Model):
    """A like on a forum post. Users can like but not dislike."""

    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="likes")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="forum_likes"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["post", "user"],
                name="forum_postlike_unique_user",
            )
        ]
        ordering = ["-created_at"]
        verbose_name = "Forum Post Like"
        verbose_name_plural = "Forum Post Likes"

    def __str__(self) -> str:
        return f"Like by {self.user} on post {self.post_id}"


class ForumConductReport(models.Model):
    """Confidential Code of Conduct report emailed to admins (Alert Admin)."""

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="forum_conduct_reports",
    )
    message = models.TextField()
    previous_page = models.CharField(max_length=500, blank=True, default="")
    reported_nickname = models.CharField(max_length=150, blank=True, default="")
    want_reply = models.BooleanField(default=False)
    reply_email = models.EmailField(blank=True, default="")
    user_agent = models.CharField(max_length=300, blank=True, default="")
    email_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Forum conduct report"
        verbose_name_plural = "Forum conduct reports"

    def __str__(self) -> str:
        preview = (self.message or "")[:60]
        return f"Conduct report {self.pk}: {preview}"
