from django.contrib.auth.base_user import BaseUserManager
from django.utils.translation import gettext_lazy as _


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        """
        Create and save a staff/admin user with the given email and password.
        This path is only used for is_staff=True admin accounts.
        Regular site users are created via get_or_create_token_user() without any email.
        """
        if not email:
            raise ValueError(_("Staff accounts must have an email address."))

        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        return user

    def get_or_create_token_user(self, token=None):
        """
        Create or retrieve an anonymous user identified solely by a downloadable passkey token.
        No email, name, or password is ever stored for these users.
        """
        import secrets

        if token:
            user = self.model.objects.filter(token=token).first()
            if user:
                return user, False
        else:
            token = secrets.token_hex(16)

        username = f"Anon-{token[:6]}"
        # No email is set — anonymous passkey users have no personal data on the server.
        user = self.model(
            email=None,
            username=username,
            token=token,
            first_name="",
            last_name="",
            is_active=True,
        )
        user.set_unusable_password()
        user.save(using=self._db)
        return user, True

    def create_superuser(self, email, password, **extra_fields):
        """
        Create and save a SuperUser with the given email and password.
        Superusers always require an email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError(_("Superuser must have is_staff=True."))
        if extra_fields.get("is_superuser") is not True:
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)
