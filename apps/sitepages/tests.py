from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.sitepages.middleware import SESSION_KEY
from apps.sitepages.models import FeedbackSubmission, NewsUpdate


class SitepagesTests(TestCase):
	def test_home_page_points_into_practice(self):
		response = self.client.get(reverse("home"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Jim's Data Gym")
		self.assertContains(response, "Ready to train?")
		self.assertContains(response, reverse("about"))
		self.assertContains(response, reverse("exercises:list"))

	def test_about_page_shows_news_and_how_to_gym_link(self):
		NewsUpdate.objects.create(
			title="Gym update",
			body="Practice notes for this week.",
			is_published=True,
		)
		response = self.client.get(reverse("about"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "About the Gym")
		self.assertContains(response, "Latest from Jim")
		self.assertContains(response, "Gym update")
		self.assertContains(response, reverse("how_to_gym"))

	def test_trainers_page_introduces_james_and_zack(self):
		response = self.client.get(reverse("about_trainers"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Trainers")
		self.assertContains(response, "James")
		self.assertContains(response, "Zack")
		self.assertContains(response, "Zacharias Voulgaris")
		self.assertContains(response, "imgs/zack.png")
		self.assertContains(response, "Super Data Science")

	def test_how_to_gym_has_video_placeholder(self):
		response = self.client.get(reverse("how_to_gym"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "How to Gym")
		self.assertContains(response, "Video coming soon")

	def test_feedback_link_present_on_pages(self):
		response = self.client.get(reverse("home"))
		self.assertContains(response, reverse("feedback"))

	@override_settings(
		EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
		FEEDBACK_TO_EMAIL="admin@example.com",
		DEFAULT_FROM_EMAIL="noreply@example.com",
	)
	def test_feedback_is_saved_and_emailed(self):
		response = self.client.post(
			reverse("feedback"),
			{
				"previous_page": "/exercises/pandas-introduction/",
				"message": "The Spotter button was really helpful on medium difficulty.",
				"want_reply": "on",
				"email": "learner@example.com",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(
			response,
			"Thank you so much for your feedback. It helps us make the platform better and we will be in touch shortly.",
		)

		submission = FeedbackSubmission.objects.get()
		self.assertEqual(submission.previous_page, "/exercises/pandas-introduction/")
		self.assertTrue(submission.want_reply)
		self.assertEqual(submission.reply_email, "learner@example.com")
		self.assertTrue(submission.email_sent)

		self.assertEqual(len(mail.outbox), 1)
		sent = mail.outbox[0]
		self.assertEqual(sent.to, ["admin@example.com"])
		self.assertIn("/exercises/pandas-introduction/", sent.body)
		self.assertEqual(sent.reply_to, ["learner@example.com"])

	@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
	def test_feedback_thanks_without_reply_omits_follow_up_clause(self):
		response = self.client.post(
			reverse("feedback"),
			{
				"previous_page": "/forum/",
				"message": "Just wanted to say the landing page looks clear and welcoming.",
				"want_reply": "",
				"email": "",
			},
			follow=True,
		)
		self.assertContains(
			response,
			"Thank you so much for your feedback. It helps us make the platform better.",
		)
		self.assertNotContains(response, "we will be in touch shortly")
		self.assertTrue(FeedbackSubmission.objects.filter(want_reply=False).exists())

	def test_feedback_requires_email_when_reply_requested(self):
		response = self.client.post(
			reverse("feedback"),
			{
				"previous_page": "/forum/",
				"message": "Please get back to me about the forum passkey flow.",
				"want_reply": "on",
				"email": "",
			},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Please enter an email address")
		self.assertFalse(FeedbackSubmission.objects.exists())

	@override_settings(
		EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
		FEEDBACK_TO_EMAIL="admin@example.com",
		DEFAULT_FROM_EMAIL="noreply@example.com",
	)
	def test_bug_report_from_exercise_is_tagged(self):
		response = self.client.get(
			reverse("feedback"),
			{"from": "/exercises/pandas-introduction/", "type": "bug"},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Report a Bug")
		self.assertContains(response, "What went wrong?")

		response = self.client.post(
			reverse("feedback") + "?type=bug",
			{
				"previous_page": "/exercises/pandas-introduction/",
				"feedback_type": "bug",
				"message": "Evaluate button did nothing after I filled missing values.",
				"want_reply": "",
				"email": "",
			},
			follow=True,
		)
		self.assertEqual(response.status_code, 200)
		submission = FeedbackSubmission.objects.get()
		self.assertTrue(submission.message.startswith("[Bug]"))
		self.assertEqual(len(mail.outbox), 1)
		self.assertEqual(mail.outbox[0].subject, "Bug report")


@override_settings(SITE_ACCESS_PASSWORD="redischoolstudent")
class SiteAccessGateTests(TestCase):
	def test_gate_page_shows_welcome_prompt(self):
		response = self.client.get(reverse("site_gate"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "Training Analytical Judgment Through Deliberate Practice")
		self.assertContains(response, "Enter the gym")
		self.assertContains(response, "Impressum")
		self.assertContains(response, "Cookie consent")
		self.assertContains(response, 'id="gdpr-cookie-banner"', html=False)

	def test_home_redirects_to_gate_when_locked(self):
		response = self.client.get(reverse("home"))
		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("site_gate"), response["Location"])

	def test_legal_pages_remain_reachable_when_locked(self):
		for name in ("privacy_policy", "cookie_policy", "terms_of_service", "imprint", "impressum"):
			response = self.client.get(reverse(name))
			self.assertEqual(response.status_code, 200, msg=name)
			self.assertContains(response, "Cookie consent")

	def test_correct_password_unlocks_site(self):
		response = self.client.post(
			reverse("site_gate"),
			{"password": "redischoolstudent", "next": "/how-to-gym/"},
		)
		self.assertRedirects(response, "/how-to-gym/", fetch_redirect_response=False)
		self.assertTrue(self.client.session.get(SESSION_KEY))

		home = self.client.get(reverse("home"))
		self.assertEqual(home.status_code, 200)

	def test_wrong_password_stays_on_gate(self):
		response = self.client.post(
			reverse("site_gate"),
			{"password": "wrong-password"},
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, "That password wasn&#x27;t right", html=False)
		self.assertFalse(self.client.session.get(SESSION_KEY))

	def test_rejects_external_next_url(self):
		response = self.client.post(
			reverse("site_gate"),
			{"password": "redischoolstudent", "next": "https://evil.example/phish"},
		)
		self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
