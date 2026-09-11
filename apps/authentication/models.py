from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from project_core.utils import TimeStampMixin

from .managers import CustomUserManager


class CustomUser(AbstractBaseUser, PermissionsMixin, TimeStampMixin):
    email = models.EmailField(
        _("email address"),
        unique=True,
        null=True,
        blank=True,
        help_text=_("Required for staff/admin accounts only. Not collected for regular users."),
        error_messages={
            "unique": _("A user with that email already exists."),
        },
    )
    username = models.CharField(
        _("username"),
        max_length=150,
        blank=True,
        null=True,
        help_text=_(
            "Optional. 150 characters or fewer. Letters, digits and @/./+/-/_ only."
        ),
        unique=True,
    )
    first_name = models.CharField(
        _("first name"),
        max_length=150,
        blank=True,
        help_text=_("Optional. Enter your first name."),
    )
    last_name = models.CharField(
        _("last name"),
        max_length=150,
        blank=True,
        help_text=_("Optional. Enter your last name."),
    )
    token = models.CharField(
        _("passkey token"),
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        help_text=_("Downloadable passkey token for identifying returning forum users. No email or password required."),
    )
    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_("Designates whether this user should be treated as active."),
    )

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]

    def __str__(self):
        return self.get_display_name()

    def get_display_name(self):
        if self.username:
            return self.username
        full_name = self.get_full_name()
        if full_name:
            return full_name
        if self.token:
            return f"Anon-{self.token[:6]}"
        if self.email:
            return self.email
        return f"User-{self.pk}"

    def get_full_name(self):
        full_name = f"{self.first_name} {self.last_name}"
        return full_name.strip()


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
        help_text=_("The user this profile belongs to."),
    )
    nickname = models.CharField(
        max_length=40,
        unique=True,
        blank=False,
        null=False,
        help_text=_("A public nickname that must be unique across the platform."),
    )
    photo = models.ImageField(
        upload_to="profile_photos/",
        blank=True,
        null=True,
        help_text=_("Optional profile photo."),
    )
    short_description = models.CharField(
        max_length=180,
        blank=True,
        default="",
        help_text=_("A short sentence about who you are."),
    )
    motivation = models.TextField(
        blank=True,
        default="",
        help_text=_("Tell others why you are interested in data analysis."),
    )
    data_field = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Preferred data science field for exercise datasets."),
    )
    dataset_file = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=_("Selected parquet dataset file for this learner's exercises."),
    )
    exercise_progress = models.JSONField(
        blank=True,
        default=dict,
        help_text=_("Per-exercise personal data state used to repeat saved attempts."),
    )
    onboarding_complete = models.BooleanField(
        default=False,
        help_text=_("Whether the learner has completed their first-login exercise data selection."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "user profile"
        verbose_name_plural = "user profiles"
        ordering = ["nickname"]

    def __str__(self):
        return self.nickname

