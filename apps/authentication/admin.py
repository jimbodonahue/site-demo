from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.translation import gettext_lazy as _

from .models import CustomUser, UserProfile


class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = (
        "get_display_name",
        "email",
        "username",
        "token",
        "is_staff",
        "is_active",
        "created_at",
    )
    list_filter = ("is_staff", "is_active")

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
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
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


admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(UserProfile)
