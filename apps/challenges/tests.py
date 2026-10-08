from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.authentication.models import CustomUser
from apps.challenges.models import Contest, Submission, SubmissionUpvote
from apps.challenges.utils import ensure_current_week, ensure_week, iso_week_for


def _png_file(name="chart.png", size=(64, 40), color=(30, 144, 255)):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class WeeklyChallengesTests(TestCase):
    def test_index_creates_current_week_contests(self):
        response = self.client.get(reverse("challenges:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Weekly Challenges")
        self.assertContains(response, "Weekly Data Viz")
        self.assertContains(response, "Resource of the Week")
        self.assertContains(response, "Misleading Headline")

        week = ensure_current_week()
        self.assertEqual(week.contests.count(), 3)
        self.assertTrue(week.contests.filter(kind=Contest.KIND_DATA_VIZ).exists())
        self.assertTrue(week.contests.filter(kind=Contest.KIND_RESOURCE).exists())
        self.assertTrue(week.contests.filter(kind=Contest.KIND_MISLEADING_HEADLINE).exists())

    def test_submit_resource_link(self):
        week = ensure_current_week()
        contest = week.contests.get(kind=Contest.KIND_RESOURCE)
        response = self.client.post(
            reverse("challenges:index"),
            {
                "contest_id": contest.pk,
                "title": "Pandas User Guide",
                "url": "https://pandas.pydata.org/docs/",
                "notes": "Great reference",
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(contest=contest)
        self.assertEqual(submission.title, "Pandas User Guide")
        self.assertEqual(submission.url, "https://pandas.pydata.org/docs/")
        self.assertTrue(submission.author.token)

    def test_submit_misleading_headline(self):
        week = ensure_current_week()
        contest = week.contests.get(kind=Contest.KIND_MISLEADING_HEADLINE)
        response = self.client.post(
            reverse("challenges:index"),
            {
                "contest_id": contest.pk,
                "title": "Study proves chocolate cures everything",
                "url": "https://example.com/headline",
                "notes": "Tiny sample, no control group, and correlation ≠ causation.",
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(contest=contest)
        self.assertEqual(submission.title, "Study proves chocolate cures everything")
        self.assertIn("correlation", submission.notes)

    def test_submit_data_viz_png(self):
        week = ensure_current_week()
        contest = week.contests.get(kind=Contest.KIND_DATA_VIZ)
        response = self.client.post(
            reverse("challenges:index"),
            {
                "contest_id": contest.pk,
                "title": "Sales heatmap",
                "notes": "Missing values shown in grey",
                "image": _png_file(),
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = Submission.objects.get(contest=contest)
        self.assertEqual(submission.title, "Sales heatmap")
        self.assertTrue(submission.image.name.endswith(".png"))

    def test_reject_non_png_for_data_viz(self):
        week = ensure_current_week()
        contest = week.contests.get(kind=Contest.KIND_DATA_VIZ)
        jpeg = SimpleUploadedFile("chart.jpg", b"not-a-real-jpeg", content_type="image/jpeg")
        response = self.client.post(
            reverse("challenges:index"),
            {
                "contest_id": contest.pk,
                "title": "Bad file",
                "image": jpeg,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Submission.objects.filter(contest=contest).exists())

    def test_closed_week_rejects_submissions(self):
        year, week_num = iso_week_for()
        # Use a prior ISO week
        from datetime import date, timedelta

        prior = date.fromisocalendar(year, week_num, 1) - timedelta(days=7)
        prior_year, prior_week = prior.isocalendar()[0], prior.isocalendar()[1]
        week = ensure_week(prior_year, prior_week)
        contest = week.contests.get(kind=Contest.KIND_RESOURCE)
        response = self.client.post(
            week.get_absolute_url(),
            {
                "contest_id": contest.pk,
                "title": "Too late",
                "url": "https://example.com/",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Submission.objects.filter(contest=contest).exists())

    def test_toggle_upvote(self):
        week = ensure_current_week()
        contest = week.contests.get(kind=Contest.KIND_RESOURCE)
        user, _ = CustomUser.objects.get_or_create_token_user()
        submission = Submission.objects.create(
            contest=contest,
            author=user,
            title="Cool tool",
            url="https://example.com/tool",
        )
        url = reverse("challenges:toggle_upvote", args=[submission.pk])

        first = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["upvoted"])
        self.assertEqual(first.json()["upvote_count"], 1)
        self.assertEqual(SubmissionUpvote.objects.filter(submission=submission).count(), 1)

        second = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertFalse(second.json()["upvoted"])
        self.assertEqual(second.json()["upvote_count"], 0)
