from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .deletion import complete_account_deletion
from .models import (
    AccountDeletionRequest,
    Connection,
    ContactShareCooldown,
    CustomUser,
    Notification,
    UserBlock,
    UserProfile,
)


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        "get_display_name",
        "email",
        "username",
        "token",
        "is_staff",
        "is_forum_moderator",
        "is_forum_suspended",
        "is_active",
        "created_at",
    )
    list_filter = ("is_staff", "is_forum_moderator", "is_forum_suspended", "is_active")

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        (_("Passkey Identity"), {"fields": ("token",)}),
        (_("Personal info (admin only)"), {"fields": ("first_name", "last_name")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_forum_moderator",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            _("Forum suspension"),
            {
                "fields": (
                    "is_forum_suspended",
                    "forum_suspended_until",
                    "forum_suspension_note",
                ),
                "description": _(
                    "Suspend forum participation only. The learner can still use exercises."
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        (
            _("Staff account (email + password required)"),
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    search_fields = ("email", "username", "token")
    ordering = ("-created_at",)


@admin.register(AccountDeletionRequest)
class AccountDeletionRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "display_name",
        "reason",
        "status",
        "requested_at",
        "scheduled_delete_at",
        "completed_at",
        "completed_by",
        "email_sent",
    )
    list_filter = ("status", "reason", "email_sent", "requested_at")
    search_fields = ("display_name", "token_hint", "details", "feedback")
    readonly_fields = (
        "requested_at",
        "completed_at",
        "completed_by",
        "email_sent",
        "user_agent",
    )
    actions = ("delete_accounts_now",)

    @admin.action(description=_("Delete selected user accounts now"))
    def delete_accounts_now(self, request, queryset):
        done = 0
        for row in queryset.filter(status=AccountDeletionRequest.STATUS_PENDING):
            if complete_account_deletion(row, completed_by="admin"):
                done += 1
        self.message_user(
            request,
            _("Deleted %(count)d account(s).") % {"count": done},
            level=messages.SUCCESS if done else messages.WARNING,
        )


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(UserProfile)
admin.site.register(Connection)
admin.site.register(UserBlock)
admin.site.register(Notification)
admin.site.register(ContactShareCooldown)
