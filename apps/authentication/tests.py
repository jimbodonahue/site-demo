from io import BytesIO

from PIL import Image
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authentication.models import CustomUser, UserProfile


class LegalAndCookiePagesTests(TestCase):
    def test_cookie_policy_page_is_available(self):
        response = self.client.get(reverse("cookie_policy"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cookie Policy")

    def test_imprint_pages_are_available_in_english_and_german(self):
        english = self.client.get(reverse("imprint"))
        self.assertEqual(english.status_code, 200)
        self.assertContains(english, "Imprint")
        self.assertContains(english, "James Donahue")
        self.assertContains(english, "Vogelhuettendeich 114")
        self.assertContains(english, "hello@jimsdatagym.com")

        german = self.client.get(reverse("impressum"))
        self.assertEqual(german.status_code, 200)
        self.assertContains(german, "Impressum")
        self.assertContains(german, "James Donahue")
        self.assertContains(german, "hello@jimsdatagym.com")


class UserProfileTests(TestCase):
    def test_membership_page_creates_passkey_identity(self):
        response = self.client.get(reverse("membership"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Account")
        self.assertContains(response, "identification token")
        self.assertContains(response, "Badges")
        self.assertContains(response, reverse("badges:index"))
        self.assertTrue(self.client.session.get("forum_token"))
        self.assertContains(response, self.client.session["forum_token"])

    def test_profile_url_still_serves_membership_page(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Account")

    def test_first_login_redirects_to_onboarding(self):
        user = CustomUser.objects.create_user(
            email="newstudent@example.com",
            username="newstudent",
            password="StrongPass123!",
        )

        response = self.client.post(
            reverse("login"),
            {"username": user.email, "password": "StrongPass123!"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("onboarding"))

    def test_onboarding_records_field_and_dataset_selection(self):
        user = CustomUser.objects.create_user(
            email="selection@example.com",
            username="selectionstudent",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        response = self.client.post(
            reverse("onboarding"),
            {
                "topic_1": "healthcare",
                "topic_2": "finance",
                "topic_3": "sports",
                "topic_4": "",
                "topic_5": "",
                "dataset_file": "01_heart_disease_cleveland.parquet",
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("home"))
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.data_field, "healthcare")
        self.assertEqual(
            user.profile.preferred_topics,
            ["healthcare", "finance", "sports"],
        )
        self.assertEqual(user.profile.primary_topic(), "healthcare")
        self.assertEqual(user.profile.dataset_file, "01_heart_disease_cleveland.parquet")
        self.assertTrue(user.profile.onboarding_complete)

    def test_onboarding_rejects_duplicate_ranked_topics(self):
        user = CustomUser.objects.create_user(
            email="dupes@example.com",
            username="dupestudent",
            password="StrongPass123!",
        )
        self.client.force_login(user)
        response = self.client.post(
            reverse("onboarding"),
            {
                "topic_1": "healthcare",
                "topic_2": "healthcare",
                "topic_3": "",
                "topic_4": "",
                "topic_5": "",
                "dataset_file": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "unique")
        user.refresh_from_db()
        profile = getattr(user, "profile", None)
        if profile is not None:
            self.assertFalse(profile.onboarding_complete)

    def test_user_can_create_profile_with_unique_nickname(self):
        user = CustomUser.objects.create_user(
            email="student@example.com",
            username="student01",
            password="StrongPass123!",
        )
        self.client.force_login(user)

        image_buffer = BytesIO()
        Image.new("RGB", (12, 12), color="blue").save(image_buffer, format="PNG")
        image_bytes = image_buffer.getvalue()
        payload = {
            "nickname": "DataNerd",
            "short_description": "Curious about patterns in messy data.",
            "motivation": "Background in biology. Python and R experience. Hiking on weekends.",
            "photo": SimpleUploadedFile("avatar.png", image_bytes, content_type="image/png"),
        }

        response = self.client.post(reverse("membership"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("membership"))
        profile = UserProfile.objects.get(user=user, nickname="DataNerd")
        self.assertTrue(profile.photo)
        self.assertIn("Hiking", profile.motivation)
        user.refresh_from_db()
        self.assertEqual(user.get_display_name(), "DataNerd")

    def test_duplicate_nickname_is_rejected(self):
        first_user = CustomUser.objects.create_user(
            email="first@example.com",
            username="first-user",
            password="StrongPass123!",
        )
        second_user = CustomUser.objects.create_user(
            email="second@example.com",
            username="second-user",
            password="StrongPass123!",
        )
        UserProfile.objects.create(
            user=first_user,
            nickname="DataNerd",
            short_description="First profile",
            motivation="Learning data analysis.",
        )

        self.client.force_login(second_user)
        response = self.client.post(
            reverse("membership"),
            {
                "nickname": "DataNerd",
                "short_description": "Second profile",
                "motivation": "More learning.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This nickname is already in use.")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_email_passkey_sends_mail_without_storing_email(self):
        user, _ = CustomUser.objects.get_or_create_token_user(token="a" * 32)
        session = self.client.session
        session["forum_token"] = user.token
        session.save()
        self.client.force_login(user)

        response = self.client.post(
            reverse("email_passkey"),
            {"email": "backup@example.com"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("membership"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["backup@example.com"])
        self.assertIn(user.token, mail.outbox[0].body)

        user.refresh_from_db()
        self.assertIsNone(user.email)
        self.assertFalse(
            CustomUser.objects.filter(email="backup@example.com").exists()
        )


class ConnectionFeatureTests(TestCase):
    def setUp(self):
        self.alice, _ = CustomUser.objects.get_or_create_token_user(token="b" * 32)
        self.bob, _ = CustomUser.objects.get_or_create_token_user(token="c" * 32)
        self.alice_profile = UserProfile.objects.create(user=self.alice, nickname="AliceData")
        self.bob_profile = UserProfile.objects.create(user=self.bob, nickname="BobStats")

    def _login_as(self, user):
        session = self.client.session
        session["forum_token"] = user.token
        session.save()
        self.client.force_login(user)

    def test_connect_notifies_recipient(self):
        self._login_as(self.alice)
        response = self.client.post(reverse("request_connection", kwargs={"nickname": "BobStats"}))
        self.assertRedirects(response, reverse("public_profile", kwargs={"nickname": "BobStats"}))

        from apps.authentication.models import Connection, Notification

        connection = Connection.objects.get(requester=self.alice, recipient=self.bob)
        self.assertEqual(connection.status, Connection.STATUS_PENDING)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.bob,
                actor=self.alice,
                notification_type=Notification.TYPE_CONNECTION_REQUEST,
            ).exists()
        )

    def test_accept_allows_ephemeral_contact_share_with_cooldown(self):
        from apps.authentication.models import ContactShareCooldown, Notification

        self._login_as(self.alice)
        self.client.post(reverse("request_connection", kwargs={"nickname": "BobStats"}))

        self._login_as(self.bob)
        notification = Notification.objects.get(recipient=self.bob)
        self.client.post(
            reverse("respond_connection", kwargs={"notification_id": notification.pk}),
            {"action": "accept"},
        )

        self._login_as(self.alice)
        response = self.client.post(
            reverse("share_contact", kwargs={"nickname": "BobStats"}),
            {"contact_details": "alice@example.com / @alice"},
        )
        self.assertRedirects(response, reverse("public_profile", kwargs={"nickname": "BobStats"}))

        share_note = Notification.objects.get(
            recipient=self.bob,
            notification_type=Notification.TYPE_CONTACT_SHARED,
        )
        self.assertEqual(share_note.contact_payload, "alice@example.com / @alice")
        self.assertTrue(
            ContactShareCooldown.objects.filter(sender=self.alice, recipient=self.bob).exists()
        )

        blocked_retry = self.client.post(
            reverse("share_contact", kwargs={"nickname": "BobStats"}),
            {"contact_details": "again@example.com"},
        )
        self.assertRedirects(blocked_retry, reverse("public_profile", kwargs={"nickname": "BobStats"}))
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.bob,
                notification_type=Notification.TYPE_CONTACT_SHARED,
            ).count(),
            1,
        )

        self._login_as(self.bob)
        reveal = self.client.post(reverse("reveal_contact", kwargs={"notification_id": share_note.pk}))
        self.assertEqual(reveal.status_code, 200)
        self.assertContains(reveal, "alice@example.com / @alice")

        share_note.refresh_from_db()
        self.assertEqual(share_note.contact_payload, "")

        again = self.client.post(reverse("reveal_contact", kwargs={"notification_id": share_note.pk}))
        self.assertRedirects(again, reverse("notifications"))

    def test_block_is_silent_and_prevents_notification(self):
        from apps.authentication.models import Notification, UserBlock

        self._login_as(self.bob)
        self.client.post(reverse("block_user", kwargs={"nickname": "AliceData"}))
        self.assertTrue(UserBlock.objects.filter(blocker=self.bob, blocked=self.alice).exists())

        self._login_as(self.alice)
        response = self.client.post(reverse("request_connection", kwargs={"nickname": "BobStats"}))
        self.assertRedirects(response, reverse("public_profile", kwargs={"nickname": "BobStats"}))
        self.assertFalse(
            Notification.objects.filter(recipient=self.bob, actor=self.alice).exists()
        )
        # Blocked user must not be told they were blocked.
        follow = self.client.get(reverse("public_profile", kwargs={"nickname": "BobStats"}))
        self.assertNotContains(follow, "blocked", status_code=200)
        self.assertContains(follow, "Request pending")

    def test_public_profile_page_renders(self):
        response = self.client.get(reverse("public_profile", kwargs={"nickname": "AliceData"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AliceData")
        self.assertContains(response, "Connect")

    def test_public_profile_shows_earned_badges(self):
        from apps.badges.models import UserBadge
        from apps.badges.services import ensure_badge_catalog

        ensure_badge_catalog()
        from apps.badges.models import Badge

        badge = Badge.objects.filter(is_active=True).first()
        UserBadge.objects.create(user=self.alice, badge=badge)
        response = self.client.get(reverse("public_profile", kwargs={"nickname": "AliceData"}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, badge.name)


class AccountDeletionTests(TestCase):
    def test_membership_shows_delete_account_link(self):
        response = self.client.get(reverse("membership"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete account")
        self.assertContains(response, reverse("delete_account"))

    def test_delete_form_requires_confirmation(self):
        self.client.get(reverse("membership"))
        response = self.client.post(
            reverse("delete_account"),
            {
                "reason": "not_using",
                "details": "Moving on",
                "feedback": "Great site though",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "confirm")
        from apps.authentication.models import AccountDeletionRequest

        self.assertFalse(AccountDeletionRequest.objects.exists())

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_delete_account_schedules_and_notifies_admin(self):
        from datetime import timedelta

        from django.utils import timezone

        from apps.authentication.models import AccountDeletionRequest

        self.client.get(reverse("membership"))
        token = self.client.session["forum_token"]
        user = CustomUser.objects.get(token=token)

        response = self.client.post(
            reverse("delete_account"),
            {
                "reason": "privacy",
                "details": "Prefer less data online",
                "feedback": "Please keep the exercises free",
                "confirm": "on",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "within 48 hours")
        self.assertContains(response, "Deletion requested")

        request_row = AccountDeletionRequest.objects.get()
        self.assertEqual(request_row.user_id, user.pk)
        self.assertEqual(request_row.reason, "privacy")
        self.assertEqual(request_row.details, "Prefer less data online")
        self.assertEqual(request_row.feedback, "Please keep the exercises free")
        self.assertTrue(request_row.email_sent)
        self.assertAlmostEqual(
            request_row.scheduled_delete_at.timestamp(),
            (timezone.now() + timedelta(hours=48)).timestamp(),
            delta=120,
        )
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Account deletion", mail.outbox[0].subject)
        self.assertIn("privacy", mail.outbox[0].body.lower())

    def test_due_deletion_is_purged_automatically(self):
        from datetime import timedelta

        from django.core.management import call_command
        from django.utils import timezone

        from apps.authentication.models import AccountDeletionRequest

        user, _ = CustomUser.objects.get_or_create_token_user()
        UserProfile.objects.create(user=user, nickname="GoneSoon")
        request_row = AccountDeletionRequest.objects.create(
            user=user,
            display_name="GoneSoon",
            token_hint=(user.token or "")[:8],
            reason=AccountDeletionRequest.REASON_OTHER,
            scheduled_delete_at=timezone.now() - timedelta(minutes=1),
        )
        user.is_active = False
        user.save(update_fields=["is_active"])

        call_command("purge_account_deletions")

        self.assertFalse(CustomUser.objects.filter(pk=user.pk).exists())
        request_row.refresh_from_db()
        self.assertEqual(request_row.status, AccountDeletionRequest.STATUS_COMPLETED)
        self.assertEqual(request_row.completed_by, "auto")
        self.assertIsNone(request_row.user_id)

    def test_inactive_passkey_cannot_be_restored(self):
        user, token = CustomUser.objects.get_or_create_token_user()
        user.is_active = False
        user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("forum:restore_token"),
            {"token_input": token, "next": reverse("membership")},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(self.client.session.get("forum_token"), token)

