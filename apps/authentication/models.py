from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from project_core.utils import TimeStampMixin

from .managers import CustomUserManager

MAX_FORUM_MODERATORS = 5


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
    is_forum_moderator = models.BooleanField(
        _("forum moderator"),
        default=False,
        help_text=_(
            "Designates forum moderators who can remove posts and notify authors "
            "about Terms of Service violations. At most five users."
        ),
    )
    is_forum_suspended = models.BooleanField(
        _("forum suspended"),
        default=False,
        help_text=_(
            "When set, this user cannot post, like, or create forum topics. "
            "Exercise access is unaffected."
        ),
    )
    forum_suspended_until = models.DateTimeField(
        _("forum suspended until"),
        null=True,
        blank=True,
        help_text=_("Optional end time for a temporary forum suspension. Leave blank for indefinite."),
    )
    forum_suspension_note = models.TextField(
        _("forum suspension note"),
        blank=True,
        default="",
        help_text=_("Internal moderator/admin note about why forum access was suspended."),
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

    def clean(self):
        super().clean()
        if not self.is_forum_moderator:
            return
        others = type(self).objects.filter(is_forum_moderator=True)
        if self.pk:
            others = others.exclude(pk=self.pk)
        if others.count() >= MAX_FORUM_MODERATORS:
            raise ValidationError(
                {
                    "is_forum_moderator": _(
                        "At most %(limit)d forum moderators are allowed. "
                        "Unset the role on another user first."
                    )
                    % {"limit": MAX_FORUM_MODERATORS}
                }
            )

    def get_display_name(self):
        profile = getattr(self, "profile", None)
        if profile and profile.nickname:
            return profile.nickname
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

    def can_use_forum(self) -> bool:
        """Return whether this user may participate in the forum (post/like/create)."""
        if not self.is_forum_suspended:
            return True
        if self.forum_suspended_until and timezone.now() >= self.forum_suspended_until:
            self.is_forum_suspended = False
            self.forum_suspended_until = None
            self.save(update_fields=["is_forum_suspended", "forum_suspended_until", "updated_at"])
            return True
        return False

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
        help_text=_("Optional one-line intro shown with your nickname."),
    )
    motivation = models.TextField(
        blank=True,
        default="",
        help_text=_(
            "Optional About Me: background, programming and statistical experience, "
            "and non-technical hobbies."
        ),
    )
    data_field = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_("Primary (rank-1) preferred data science field for exercise datasets."),
    )
    preferred_topics = models.JSONField(
        blank=True,
        default=list,
        help_text=_(
            "Up to five preferred Data Zoo topics in ranked order. "
            "The first entry is the default used for new exercise attempts."
        ),
    )
    dataset_file = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text=_("Optional preferred parquet dataset file for the primary topic."),
    )
    exercise_progress = models.JSONField(
        blank=True,
        default=dict,
        help_text=_(
            "Per-exercise personal data state and prior attempt history "
            "used to repeat previous attempts."
        ),
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

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("public_profile", kwargs={"nickname": self.nickname})

    def ranked_topics(self) -> list[str]:
        """Return unique preferred zoo topics in rank order (max 5)."""
        from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS

        ranked: list[str] = []
        raw = self.preferred_topics if isinstance(self.preferred_topics, list) else []
        for item in raw:
            topic = str(item or "").strip().lower()
            if topic in DATA_SCIENCE_SECTORS and topic not in ranked:
                ranked.append(topic)
            if len(ranked) >= 5:
                break
        # Backward compatibility: older profiles only have data_field.
        if not ranked:
            legacy = str(self.data_field or "").strip().lower()
            if legacy in DATA_SCIENCE_SECTORS:
                ranked = [legacy]
        return ranked

    def primary_topic(self) -> str:
        """Rank-1 preferred topic, or empty string if unset."""
        ranked = self.ranked_topics()
        return ranked[0] if ranked else ""

    def set_ranked_topics(self, topics: list[str]) -> None:
        """Store ranked topics and keep ``data_field`` synced to rank 1."""
        from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS

        ranked: list[str] = []
        for item in topics or []:
            topic = str(item or "").strip().lower()
            if topic in DATA_SCIENCE_SECTORS and topic not in ranked:
                ranked.append(topic)
            if len(ranked) >= 5:
                break
        self.preferred_topics = ranked
        self.data_field = ranked[0] if ranked else ""


class Connection(models.Model):
    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_ACCEPTED, "Accepted"),
        (STATUS_DECLINED, "Declined"),
    ]

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="connection_requests_sent",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="connection_requests_received",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["requester", "recipient"],
                name="unique_connection_pair",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.requester_id} → {self.recipient_id} ({self.status})"

    def involves(self, user):
        return user.pk in (self.requester_id, self.recipient_id)

    def other_user(self, user):
        if user.pk == self.requester_id:
            return self.recipient
        if user.pk == self.recipient_id:
            return self.requester
        return None


class UserBlock(models.Model):
    blocker = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_initiated",
    )
    blocked = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="blocks_received",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["blocker", "blocked"], name="unique_user_block"),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.blocker_id} blocked {self.blocked_id}"


class Notification(models.Model):
    TYPE_CONNECTION_REQUEST = "connection_request"
    TYPE_CONNECTION_ACCEPTED = "connection_accepted"
    TYPE_CONTACT_SHARED = "contact_shared"
    TYPE_FORUM_VIOLATION = "forum_violation"
    TYPE_CHOICES = [
        (TYPE_CONNECTION_REQUEST, "Connection request"),
        (TYPE_CONNECTION_ACCEPTED, "Connection accepted"),
        (TYPE_CONTACT_SHARED, "Contact shared"),
        (TYPE_FORUM_VIOLATION, "Forum terms violation"),
    ]

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications_sent",
        null=True,
        blank=True,
    )
    notification_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    connection = models.ForeignKey(
        Connection,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
    )
    # Ephemeral contact text — cleared immediately after the recipient views it.
    contact_payload = models.TextField(blank=True, default="")
    # Durable notice text (e.g. moderator Terms of Service violation messages).
    message = models.TextField(blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.notification_type} → {self.recipient_id}"


class ContactShareCooldown(models.Model):
    """Tracks when contact details were last shared — never stores the contact text."""

    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contact_share_cooldowns_sent",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="contact_share_cooldowns_received",
    )
    last_sent_at = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["sender", "recipient"],
                name="unique_contact_share_cooldown",
            ),
        ]

    def __str__(self):
        return f"{self.sender_id} → {self.recipient_id} @ {self.last_sent_at}"


class AccountDeletionRequest(models.Model):
    """User-requested account deletion; auto-purged after 48 hours if not done manually."""

    REASON_NOT_USING = "not_using"
    REASON_TOO_HARD = "too_hard"
    REASON_PRIVACY = "privacy"
    REASON_OTHER_PLATFORM = "other_platform"
    REASON_TECHNICAL = "technical"
    REASON_COMMUNITY = "community"
    REASON_OTHER = "other"

    REASON_CHOICES = [
        (REASON_NOT_USING, _("I'm not using the site anymore")),
        (REASON_TOO_HARD, _("Content is too difficult or not the right level")),
        (REASON_PRIVACY, _("Privacy concerns")),
        (REASON_OTHER_PLATFORM, _("I found another platform")),
        (REASON_TECHNICAL, _("Technical issues")),
        (REASON_COMMUNITY, _("Community or forum concerns")),
        (REASON_OTHER, _("Other")),
    ]

    STATUS_PENDING = "pending"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_COMPLETED, _("Completed")),
        (STATUS_CANCELLED, _("Cancelled")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="account_deletion_requests",
    )
    display_name = models.CharField(max_length=200, blank=True, default="")
    token_hint = models.CharField(max_length=16, blank=True, default="")
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    details = models.TextField(
        blank=True,
        default="",
        help_text=_("Optional details about why the user is leaving."),
    )
    feedback = models.TextField(
        blank=True,
        default="",
        help_text=_("Optional feedback or complaints for the team."),
    )
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    scheduled_delete_at = models.DateTimeField(db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_("How deletion finished: auto, admin, or manual."),
    )
    email_sent = models.BooleanField(default=False)
    user_agent = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        ordering = ["-requested_at"]
        verbose_name = _("account deletion request")
        verbose_name_plural = _("account deletion requests")

    def __str__(self):
        label = self.display_name or f"user-{self.user_id or '?'}"
        return f"Deletion request {self.pk} ({label}, {self.status})"

    @property
    def is_due(self) -> bool:
        return self.status == self.STATUS_PENDING and timezone.now() >= self.scheduled_delete_at

