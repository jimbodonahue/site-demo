from django.contrib import admin

from .models import ForumConductReport, Post, PostLike, Topic


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("title", "section", "exercise", "created_by", "created_at")
    list_filter = ("section", "created_at")
    search_fields = ("title",)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("topic", "author", "created_at")
    list_filter = ("created_at",)
    search_fields = ("content", "author__username")


@admin.register(PostLike)
class PostLikeAdmin(admin.ModelAdmin):
    list_display = ("post", "user", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "post__content")


@admin.register(ForumConductReport)
class ForumConductReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "reported_nickname",
        "want_reply",
        "email_sent",
        "created_at",
    )
    list_filter = ("want_reply", "email_sent", "created_at")
    search_fields = ("message", "reported_nickname", "reply_email", "reporter__username", "reporter__token")
    readonly_fields = ("created_at",)
