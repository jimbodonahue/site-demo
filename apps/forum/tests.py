from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.authentication.models import CustomUser, UserProfile
from apps.forum.models import ForumConductReport, Post, Topic


class ForumTokenAuthTests(TestCase):
    def test_forum_auto_assigns_token_user(self):
        response = self.client.get(reverse("forum:index"))
        self.assertEqual(response.status_code, 200)

        token = self.client.session.get("forum_token")
        self.assertIsNotNone(token)

        user = CustomUser.objects.filter(token=token).first()
        self.assertIsNotNone(user)
        self.assertTrue(user.username.startswith("Anon-"))
        self.assertIsNone(user.email)

    def test_create_topic_without_email_login(self):
        response = self.client.post(
            reverse("forum:topic_create"),
            {"title": "Test Anonymous Topic"},
        )
        self.assertEqual(response.status_code, 302)

        topic = Topic.objects.get(title="Test Anonymous Topic")
        self.assertIsNotNone(topic)
        self.assertIsNotNone(topic.created_by.token)

    def test_post_reply_without_email_login(self):
        user, token = CustomUser.objects.get_or_create_token_user()
        topic = Topic.objects.create(title="Discussion Thread", created_by=user)

        response = self.client.post(
            reverse("forum:topic_detail", args=[topic.pk]),
            {"content": "This is an anonymous reply using token identity."},
        )
        self.assertEqual(response.status_code, 302)

        reply = Post.objects.get(topic=topic, content="This is an anonymous reply using token identity.")
        self.assertIsNotNone(reply)
        self.assertIsNotNone(reply.author.token)

    def test_download_token_file(self):
        response = self.client.get(reverse("forum:download_token"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json; charset=utf-8")
        self.assertIn("attachment; filename=\"django_platform_passkey", response["Content-Disposition"])
        body = response.content.decode("utf-8")
        self.assertIn("token_hint", body)
        self.assertNotIn("exercise_progress", body)

        token = self.client.session.get("forum_token")
        self.assertNotIn(token, body)

    def test_download_token_file_can_include_raw_token_when_explicit(self):
        response = self.client.get(reverse("forum:download_token") + "?include_raw_token=1")
        self.assertEqual(response.status_code, 200)

        token = self.client.session.get("forum_token")
        self.assertIn("forum_token", response.content.decode("utf-8"))
        self.assertIn(token, response.content.decode("utf-8"))

    def test_restore_token_by_string_input(self):
        user, _ = CustomUser.objects.get_or_create_token_user()
        original_token = user.token
        topic = Topic.objects.create(title="User Topic", created_by=user)

        # Clear session client
        self.client.cookies.clear()

        # Restore identity
        response = self.client.post(
            reverse("forum:restore_token"),
            {"token_input": original_token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("forum_token"), original_token)
        self.assertContains(response, "Passkey identity restored")
        self.assertNotContains(response, "localStorage.setItem")

    def test_restore_token_by_file_upload(self):
        user, _ = CustomUser.objects.get_or_create_token_user()
        original_token = user.token

        file_content = f'{{"version": 1, "forum_token": "{original_token}", "username": "{user.username}", "exercise_progress": {{}}}}'.encode("utf-8")
        uploaded_file = SimpleUploadedFile("passkey.json", file_content, content_type="application/json")

        self.client.cookies.clear()

        response = self.client.post(
            reverse("forum:restore_token"),
            {"token_file": uploaded_file},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session.get("forum_token"), original_token)
        self.assertContains(response, "Passkey identity restored")
        self.assertNotContains(response, "localStorage.setItem")


    def test_restore_invalid_token(self):
        response = self.client.post(
            reverse("forum:restore_token"),
            {"token_input": "invalid_non_existent_token_12345"},
            follow=True,
        )
        self.assertContains(response, "Invalid identity token")

    def test_restore_token_rejects_external_next(self):
        user, _ = CustomUser.objects.get_or_create_token_user()
        self.client.cookies.clear()
        response = self.client.post(
            reverse("forum:restore_token") + "?next=https://evil.example/phish",
            {"token_input": user.token},
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertNotIn("evil.example", body)
        self.assertIn("restored-next-url", body)

    def test_restore_token_ignores_legacy_progress_payload(self):
        import json

        user, _ = CustomUser.objects.get_or_create_token_user()
        evil = {"</script><script>alert(1)</script>": "x"}
        payload = json.dumps({"forum_token": user.token, "exercise_progress": evil}).encode("utf-8")
        uploaded = SimpleUploadedFile("passkey.json", payload, content_type="application/json")
        self.client.cookies.clear()
        response = self.client.post(reverse("forum:restore_token"), {"token_file": uploaded})
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertNotIn("restored-progress-data", body)
        self.assertContains(response, "Passkey identity restored")
        self.assertEqual(self.client.session.get("forum_token"), user.token)

    def test_useful_resources_topic_auto_created(self):
        response = self.client.get(reverse("forum:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Useful Resources")
        self.assertContains(response, "Exercise Discussions")
        self.assertContains(response, "Job Market Readiness")
        self.assertContains(response, "Celebrate Achievements")

        for title in ("Theory", "Programming", "Machine Learning", "Data Analysis", "Tools & Libraries"):
            topic = Topic.objects.filter(title=title, section=Topic.SECTION_RESOURCES).first()
            self.assertIsNotNone(topic, title)
            self.assertTrue(topic.posts.exists())

        programming = Topic.objects.get(title="Programming", section=Topic.SECTION_RESOURCES)
        self.assertIn("Python Documentation", programming.posts.first().content)

        self.assertTrue(Topic.objects.filter(section=Topic.SECTION_JOB_MARKET).exists())
        self.assertTrue(Topic.objects.filter(section=Topic.SECTION_ACHIEVEMENTS).exists())

    def test_auto_create_exercise_topic_on_save(self):
        from apps.exercises.models import Exercise

        exercise = Exercise.objects.create(
            title="Advanced Machine Learning Clean",
            slug="advanced-ml-clean",
            published=True,
        )
        topic = Topic.objects.filter(exercise=exercise).first()
        self.assertIsNotNone(topic)
        self.assertEqual(topic.title, "Discussion: Advanced Machine Learning Clean")


class ForumLikeTests(TestCase):
    def setUp(self):
        self.user, _ = CustomUser.objects.get_or_create_token_user()
        self.topic = Topic.objects.create(title="Likeable Topic", created_by=self.user)
        self.post = Post.objects.create(
            topic=self.topic,
            author=self.user,
            content="Please like this thoughtful reply.",
        )

    def test_topic_detail_shows_like_controls(self):
        response = self.client.get(reverse("forum:topic_detail", args=[self.topic.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Like")
        self.assertContains(response, reverse("forum:toggle_like", args=[self.post.pk]))

    def test_toggle_like_adds_and_removes_like(self):
        from apps.forum.models import PostLike

        like_url = reverse("forum:toggle_like", args=[self.post.pk])

        first = self.client.post(like_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(first.status_code, 200)
        payload = first.json()
        self.assertTrue(payload["liked"])
        self.assertEqual(payload["like_count"], 1)
        self.assertEqual(PostLike.objects.filter(post=self.post).count(), 1)

        second = self.client.post(like_url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(second.status_code, 200)
        payload = second.json()
        self.assertFalse(payload["liked"])
        self.assertEqual(payload["like_count"], 0)
        self.assertEqual(PostLike.objects.filter(post=self.post).count(), 0)

    def test_like_is_unique_per_user(self):
        from apps.forum.models import PostLike

        like_url = reverse("forum:toggle_like", args=[self.post.pk])
        self.client.post(like_url)
        self.client.post(like_url)
        self.client.post(like_url)
        # Final state after odd number of toggles is liked once.
        self.assertEqual(PostLike.objects.filter(post=self.post).count(), 1)


class ForumModeratorTests(TestCase):
    def setUp(self):
        self.author, _ = CustomUser.objects.get_or_create_token_user()
        self.moderator, _ = CustomUser.objects.get_or_create_token_user()
        self.moderator.is_forum_moderator = True
        self.moderator.save(update_fields=["is_forum_moderator"])
        self.topic = Topic.objects.create(title="Moderation Thread", created_by=self.author)
        self.post = Post.objects.create(
            topic=self.topic,
            author=self.author,
            content="A post that breaks the community guidelines.",
        )

    def _login_as(self, user):
        session = self.client.session
        session["forum_token"] = user.token
        session.save()
        self.client.force_login(user)

    def test_moderator_badge_on_public_profile(self):
        from apps.authentication.models import UserProfile

        UserProfile.objects.create(user=self.moderator, nickname="GymMod")
        response = self.client.get(reverse("public_profile", args=["GymMod"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Moderator")

    def test_moderator_sees_remove_control(self):
        self._login_as(self.moderator)
        response = self.client.get(reverse("forum:topic_detail", args=[self.topic.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Remove (CoC)")
        self.assertContains(
            response,
            reverse("forum:moderate_delete_post", args=[self.post.pk]),
        )

    def test_non_moderator_cannot_delete_post(self):
        bystander, _ = CustomUser.objects.get_or_create_token_user()
        self._login_as(bystander)
        response = self.client.post(
            reverse("forum:moderate_delete_post", args=[self.post.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_moderator_deletes_post_and_notifies_author(self):
        from apps.authentication.models import Notification

        self._login_as(self.moderator)
        response = self.client.post(
            reverse("forum:moderate_delete_post", args=[self.post.pk]),
        )
        self.assertRedirects(response, self.topic.get_absolute_url())
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

        notice = Notification.objects.get(
            recipient=self.author,
            notification_type=Notification.TYPE_FORUM_VIOLATION,
        )
        self.assertEqual(notice.actor_id, self.moderator.pk)
        self.assertIn("Code of Conduct", notice.message)
        self.assertIn("civil", notice.message)

    def test_terms_page_covers_civil_supportive_conduct(self):
        response = self.client.get(reverse("terms_of_service"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Be civil")
        self.assertContains(response, "Be supportive")
        self.assertContains(response, "Forum moderators")

    def test_at_most_five_forum_moderators(self):
        from django.core.exceptions import ValidationError

        from apps.authentication.models import MAX_FORUM_MODERATORS

        # self.moderator already counts as one
        for i in range(MAX_FORUM_MODERATORS - 1):
            user, _ = CustomUser.objects.get_or_create_token_user()
            user.is_forum_moderator = True
            user.full_clean()
            user.save()

        sixth, _ = CustomUser.objects.get_or_create_token_user()
        sixth.is_forum_moderator = True
        with self.assertRaises(ValidationError):
            sixth.full_clean()


class ForumCodeSpoilerTests(TestCase):
    def setUp(self):
        self.user, _ = CustomUser.objects.get_or_create_token_user()
        self.topic = Topic.objects.create(title="Code Tips", created_by=self.user)

    def test_fenced_code_renders_as_spoiler_with_tooltip(self):
        from apps.forum.rendering import CODE_SPOILER_TOOLTIP

        post = Post.objects.create(
            topic=self.topic,
            author=self.user,
            content="Here is a hint:\n\n```python\nanswer = 42\n```\n",
        )
        html = str(post.render_content_html())
        self.assertIn('class="forum-code-spoiler"', html)
        self.assertIn("Show code snippet", html)
        self.assertIn(CODE_SPOILER_TOOLTIP, html)
        self.assertIn("answer = 42", html)
        self.assertIn("<pre>", html)

    def test_reply_form_offers_code_snippet_button(self):
        response = self.client.get(reverse("forum:topic_detail", args=[self.topic.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add code snippet")
        self.assertContains(
            response,
            "Tips are good, but writing your own code builds muscles faster!",
        )


class ForumCodeOfConductTests(TestCase):
    def test_code_of_conduct_page_renders(self):
        response = self.client.get(reverse("forum:code_of_conduct"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Jim's Data Gym Code of Conduct")
        self.assertContains(response, "Core Values")
        self.assertContains(response, "Alert Admin")
        self.assertContains(response, "admin@jimsdatagym.com")

    def test_forum_index_links_to_code_of_conduct_and_alert_admin(self):
        response = self.client.get(reverse("forum:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("forum:code_of_conduct"))
        self.assertContains(response, reverse("forum:alert_admin"))

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_alert_admin_sends_email_and_stores_report(self):
        from django.core import mail

        response = self.client.post(
            reverse("forum:alert_admin"),
            {
                "message": "Someone posted harassing content in a thread.",
                "reported_nickname": "BadActor",
                "want_reply": "on",
                "email": "reporter@example.com",
                "previous_page": "/forum/1/",
            },
        )
        self.assertRedirects(response, reverse("forum:alert_admin_thanks"))
        report = ForumConductReport.objects.get()
        self.assertEqual(report.reported_nickname, "BadActor")
        self.assertTrue(report.want_reply)
        self.assertEqual(report.reply_email, "reporter@example.com")
        self.assertTrue(report.email_sent)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Code of Conduct", mail.outbox[0].subject)
        self.assertIn("harassing", mail.outbox[0].body)


class ForumSuspensionTests(TestCase):
    def setUp(self):
        self.member, _ = CustomUser.objects.get_or_create_token_user()
        self.moderator, _ = CustomUser.objects.get_or_create_token_user()
        self.moderator.is_forum_moderator = True
        self.moderator.save(update_fields=["is_forum_moderator"])
        self.member_profile = UserProfile.objects.create(user=self.member, nickname="LearnerOne")
        self.topic = Topic.objects.create(title="Open Thread", created_by=self.moderator)

    def _login_as(self, user):
        session = self.client.session
        session["forum_token"] = user.token
        session.save()
        self.client.force_login(user)

    def test_suspended_user_cannot_create_topic_or_reply(self):
        self.member.is_forum_suspended = True
        self.member.save(update_fields=["is_forum_suspended"])
        self._login_as(self.member)

        create = self.client.post(reverse("forum:topic_create"), {"title": "Should fail"})
        self.assertEqual(create.status_code, 302)
        self.assertFalse(Topic.objects.filter(title="Should fail").exists())

        reply = self.client.post(
            reverse("forum:topic_detail", args=[self.topic.pk]),
            {"content": "Should also fail"},
        )
        self.assertEqual(reply.status_code, 302)
        self.assertFalse(Post.objects.filter(topic=self.topic, content="Should also fail").exists())

        detail = self.client.get(reverse("forum:topic_detail", args=[self.topic.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "forum access is suspended")

    def test_suspended_user_can_still_browse_and_open_exercises(self):
        self.member.is_forum_suspended = True
        self.member.save(update_fields=["is_forum_suspended"])
        self._login_as(self.member)

        forum = self.client.get(reverse("forum:index"))
        self.assertEqual(forum.status_code, 200)
        exercises = self.client.get(reverse("exercises:list"))
        self.assertEqual(exercises.status_code, 200)

    def test_moderator_can_suspend_and_unsuspend_from_profile(self):
        self._login_as(self.moderator)
        suspend = self.client.post(
            reverse("forum:suspend_user", args=["LearnerOne"]),
            {"days": "7", "note": "Repeated harassment"},
        )
        self.assertRedirects(suspend, reverse("public_profile", args=["LearnerOne"]))
        self.member.refresh_from_db()
        self.assertTrue(self.member.is_forum_suspended)
        self.assertIsNotNone(self.member.forum_suspended_until)
        self.assertEqual(self.member.forum_suspension_note, "Repeated harassment")

        profile = self.client.get(reverse("public_profile", args=["LearnerOne"]))
        self.assertContains(profile, "Restore forum access")

        unsuspend = self.client.post(reverse("forum:unsuspend_user", args=["LearnerOne"]))
        self.assertRedirects(unsuspend, reverse("public_profile", args=["LearnerOne"]))
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_forum_suspended)
        self.assertTrue(self.member.can_use_forum())

    def test_non_moderator_cannot_suspend(self):
        bystander, _ = CustomUser.objects.get_or_create_token_user()
        self._login_as(bystander)
        response = self.client.post(reverse("forum:suspend_user", args=["LearnerOne"]))
        self.assertEqual(response.status_code, 302)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_forum_suspended)

