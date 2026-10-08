from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.authentication.models import CustomUser
from apps.badges.models import UserBadge
from apps.badges.services import (
    TEN_HOURS_SECONDS,
    ensure_badge_catalog,
    record_exercise_run,
    record_forum_post,
    record_platform_presence,
    record_post_like_threshold,
)
from apps.exercises.models import Exercise, ExerciseAttempt, Track
from apps.forum.models import Post, PostLike, Topic


class BadgeSystemTests(TestCase):
    def setUp(self):
        ensure_badge_catalog()
        self.user, _ = CustomUser.objects.get_or_create_token_user()
        self.track = Track.objects.create(title="Badge Track", slug="badge-track", published=True)
        self.exercises = []
        for index in range(1, 6):
            self.exercises.append(
                Exercise.objects.create(
                    track=self.track,
                    title=f"Badge Exercise {index}",
                    slug=f"badge-exercise-{index}",
                    published=True,
                )
            )

    def _login_token_user(self):
        session = self.client.session
        session["forum_token"] = self.user.token
        session.save()
        self.client.force_login(self.user)

    def _request_for(self, user):
        from django.test import RequestFactory

        factory = RequestFactory()
        req = factory.post("/exercises/run/")
        req.user = user
        session = self.client.session
        session.save()
        req.session = session
        return req

    def test_gallery_renders_catalog(self):
        response = self.client.get(reverse("badges:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "First Steps")
        self.assertContains(response, "Exercise Complete")
        self.assertContains(response, "Ten Hour Club")
        self.assertContains(response, "Well-Received")
        self.assertContains(response, "Flawless Five")
        self.assertContains(response, "First Plot")
        self.assertContains(response, "Style Spark")

    def test_first_exercise_and_first_try_badges(self):
        self._login_token_user()
        exercise = self.exercises[0]
        ExerciseAttempt.objects.create(
            exercise=exercise,
            visitor_key=f"user:{self.user.pk}",
            progress_state={"passed": True},
        )
        req = self._request_for(self.user)

        awarded = record_exercise_run(req, exercise, success=True, passed=True)
        slugs = {badge.badge.slug for badge in awarded}
        self.assertIn("first-exercise", slugs)
        self.assertIn("first-try", slugs)
        self.assertIn("exercise-complete", slugs)
        self.assertTrue(UserBadge.objects.filter(user=self.user, badge__slug="first-exercise").exists())

    def test_exercise_complete_badge_is_repeatable(self):
        req = self._request_for(self.user)
        first = record_exercise_run(req, self.exercises[0], success=True, passed=True)
        second = record_exercise_run(req, self.exercises[0], success=True, passed=True)
        self.assertTrue(any(badge.badge.slug == "exercise-complete" for badge in first))
        self.assertTrue(any(badge.badge.slug == "exercise-complete" for badge in second))
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge__slug="exercise-complete").count(),
            2,
        )
        # One-time milestone badges stay unique.
        self.assertEqual(
            UserBadge.objects.filter(user=self.user, badge__slug="first-exercise").count(),
            1,
        )

    def test_ten_hours_badge_awarded_once(self):
        now = timezone.now()
        record_platform_presence(self.user, now=now - timedelta(seconds=90))
        record_platform_presence(self.user, now=now - timedelta(seconds=30))
        self.user.badge_stats.refresh_from_db()
        self.assertGreater(self.user.badge_stats.platform_seconds, 0)
        self.assertFalse(UserBadge.objects.filter(user=self.user, badge__slug="ten-hours").exists())

        self.user.badge_stats.platform_seconds = TEN_HOURS_SECONDS - 30
        self.user.badge_stats.last_seen_at = now - timedelta(seconds=60)
        self.user.badge_stats.save()
        awarded = record_platform_presence(self.user, now=now)
        self.assertTrue(any(badge.badge.slug == "ten-hours" for badge in awarded))
        awarded_again = record_platform_presence(self.user, now=now + timedelta(seconds=30))
        self.assertFalse(any(badge.badge.slug == "ten-hours" for badge in awarded_again))
        self.assertEqual(UserBadge.objects.filter(user=self.user, badge__slug="ten-hours").count(), 1)

    def test_flawless_five_streak(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        for exercise in self.exercises:
            ExerciseAttempt.objects.update_or_create(
                exercise=exercise,
                visitor_key=f"user:{self.user.pk}",
                defaults={"progress_state": {"passed": True}},
            )
            req = factory.post("/exercises/run/")
            req.user = self.user
            session = self.client.session
            session.save()
            req.session = session
            record_exercise_run(req, exercise, success=True, passed=True)

        self.assertTrue(UserBadge.objects.filter(user=self.user, badge__slug="flawless-five").exists())

    def test_forum_engagement_badges(self):
        for index in range(5):
            record_forum_post(self.user, post_id=index + 1)
        self.assertTrue(UserBadge.objects.filter(user=self.user, badge__slug="forum-newcomer").exists())
        self.assertTrue(UserBadge.objects.filter(user=self.user, badge__slug="forum-regular").exists())

    def test_well_received_badge_at_five_likes(self):
        topic = Topic.objects.create(title="Badge Topic", created_by=self.user)
        post = Post.objects.create(topic=topic, author=self.user, content="Helpful question?")
        for _ in range(5):
            liker, _ = CustomUser.objects.get_or_create_token_user()
            PostLike.objects.create(post=post, user=liker)
        awarded = record_post_like_threshold(post, post.likes.count())
        self.assertEqual(len(awarded), 1)
        self.assertEqual(awarded[0].badge.slug, "well-received")

    def test_error_resets_flawless_streak(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        session = self.client.session
        session.save()

        for exercise in self.exercises[:3]:
            ExerciseAttempt.objects.update_or_create(
                exercise=exercise,
                visitor_key=f"user:{self.user.pk}",
                defaults={"progress_state": {"passed": True}},
            )
            req = factory.post("/exercises/run/")
            req.user = self.user
            req.session = session
            record_exercise_run(req, exercise, success=True, passed=True)

        req = factory.post("/exercises/run/")
        req.user = self.user
        req.session = session
        record_exercise_run(req, self.exercises[3], success=False, passed=False)
        self.user.badge_stats.refresh_from_db()
        self.assertEqual(self.user.badge_stats.consecutive_error_free_completions, 0)

    def test_plotting_bonus_awards_plot_and_style_badges(self):
        from django.test import RequestFactory

        factory = RequestFactory()
        req = factory.post("/exercises/run/")
        req.user = self.user
        session = self.client.session
        session.save()
        req.session = session

        awarded = record_exercise_run(
            req,
            self.exercises[0],
            success=False,
            passed=False,
            plotting_bonus={
                "passed": True,
                "kind": "bar",
                "plots_created": 1,
                "modifications_count": 1,
                "modification_categories": ["color"],
            },
        )
        slugs = {badge.badge.slug for badge in awarded}
        self.assertIn("first-plot", slugs)
        self.assertIn("style-spark", slugs)
        self.user.badge_stats.refresh_from_db()
        self.assertEqual(self.user.badge_stats.plots_created_count, 1)
        self.assertEqual(self.user.badge_stats.plot_modifications_count, 1)
