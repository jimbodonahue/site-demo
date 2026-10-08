from django.db import models
from django.utils import timezone


class NewsUpdate(models.Model):
	"""Short news items shown on the About the Gym “Latest from Jim” section."""

	title = models.CharField(max_length=200)
	body = models.TextField(help_text="Plain text or light Markdown-style notes.")
	published_at = models.DateTimeField(default=timezone.now)
	is_published = models.BooleanField(default=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-published_at", "-created_at"]
		verbose_name = "news update"
		verbose_name_plural = "news updates"

	def __str__(self):
		return self.title


class FeedbackSubmission(models.Model):
	"""Stored feedback for admin review / CSV download; also emailed when possible."""

	message = models.TextField()
	previous_page = models.CharField(max_length=500, blank=True, default="")
	want_reply = models.BooleanField(default=False)
	reply_email = models.EmailField(blank=True, default="")
	user_agent = models.CharField(max_length=300, blank=True, default="")
	email_sent = models.BooleanField(
		default=False,
		help_text="Whether an email copy was sent successfully when this was submitted.",
	)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ["-created_at"]
		verbose_name = "feedback submission"
		verbose_name_plural = "feedback submissions"

	def __str__(self):
		preview = (self.message or "")[:60]
		return f"Feedback {self.pk}: {preview}"
