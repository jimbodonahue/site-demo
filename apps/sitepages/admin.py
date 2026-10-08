import csv

from django.contrib import admin
from django.http import HttpResponse

from .models import FeedbackSubmission, NewsUpdate


@admin.register(NewsUpdate)
class NewsUpdateAdmin(admin.ModelAdmin):
	list_display = ("title", "published_at", "is_published", "updated_at")
	list_filter = ("is_published",)
	search_fields = ("title", "body")
	date_hierarchy = "published_at"
	ordering = ("-published_at",)


@admin.register(FeedbackSubmission)
class FeedbackSubmissionAdmin(admin.ModelAdmin):
	list_display = (
		"created_at",
		"want_reply",
		"reply_email",
		"previous_page",
		"email_sent",
		"short_message",
	)
	list_filter = ("want_reply", "email_sent", "created_at")
	search_fields = ("message", "reply_email", "previous_page")
	readonly_fields = (
		"message",
		"previous_page",
		"want_reply",
		"reply_email",
		"user_agent",
		"email_sent",
		"created_at",
	)
	date_hierarchy = "created_at"
	ordering = ("-created_at",)
	actions = ("export_as_csv",)

	@admin.display(description="Message")
	def short_message(self, obj):
		text = obj.message or ""
		return text if len(text) <= 80 else text[:77] + "…"

	@admin.action(description="Download selected feedback as CSV")
	def export_as_csv(self, request, queryset):
		response = HttpResponse(content_type="text/csv")
		response["Content-Disposition"] = 'attachment; filename="feedback_submissions.csv"'
		writer = csv.writer(response)
		writer.writerow(
			[
				"id",
				"created_at",
				"previous_page",
				"want_reply",
				"reply_email",
				"email_sent",
				"user_agent",
				"message",
			]
		)
		for row in queryset.order_by("created_at"):
			writer.writerow(
				[
					row.pk,
					row.created_at.isoformat(),
					row.previous_page,
					row.want_reply,
					row.reply_email,
					row.email_sent,
					row.user_agent,
					row.message,
				]
			)
		return response
