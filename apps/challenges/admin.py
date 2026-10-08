from django.contrib import admin

from .models import ChallengeWeek, Contest, Submission, SubmissionUpvote


class ContestInline(admin.TabularInline):
    model = Contest
    extra = 0


@admin.register(ChallengeWeek)
class ChallengeWeekAdmin(admin.ModelAdmin):
    list_display = ("iso_year", "iso_week", "starts_on", "ends_on")
    list_filter = ("iso_year",)
    inlines = [ContestInline]


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ("kind", "week")
    list_filter = ("kind",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("title", "contest", "author", "created_at")
    list_filter = ("contest__kind", "created_at")
    search_fields = ("title", "url", "notes", "author__username")


@admin.register(SubmissionUpvote)
class SubmissionUpvoteAdmin(admin.ModelAdmin):
    list_display = ("submission", "user", "created_at")
    list_filter = ("created_at",)
