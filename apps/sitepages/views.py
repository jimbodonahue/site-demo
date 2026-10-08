import csv
import logging
from urllib.parse import urlparse

from django.conf import settings
from django.core.mail import EmailMessage
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.views.decorators.http import require_http_methods
from django.views.generic import TemplateView

from project_core.ratelimit import check_rate_limit

from .forms import FeedbackForm
from .middleware import SESSION_KEY
from .models import FeedbackSubmission, NewsUpdate

logger = logging.getLogger(__name__)


class LandingView(TemplateView):
	template_name = "sitepages/landing.html"


class AboutGymView(TemplateView):
	template_name = "sitepages/about_gym.html"

	def get_context_data(self, **kwargs):
		context = super().get_context_data(**kwargs)
		context["news_updates"] = NewsUpdate.objects.filter(is_published=True)[:5]
		return context


class TrainersView(TemplateView):
	template_name = "sitepages/trainers.html"


class HowToGymView(TemplateView):
	template_name = "sitepages/how_to_gym.html"


def _safe_next_url(candidate: str | None) -> str:
	"""Only allow same-site relative paths as post-login destinations."""
	if not candidate:
		return reverse("home")
	parsed = urlparse(candidate)
	if parsed.scheme or parsed.netloc:
		return reverse("home")
	if not candidate.startswith("/") or candidate.startswith("//"):
		return reverse("home")
	return candidate


@require_http_methods(["GET", "POST"])
def site_gate(request):
	"""Simple shared-password welcome page that unlocks the rest of the site."""
	if request.session.get(SESSION_KEY):
		return redirect(_safe_next_url(request.GET.get("next") or request.POST.get("next")))

	error = ""
	next_url = request.POST.get("next") or request.GET.get("next") or ""

	if request.method == "POST":
		allowed, _retry = check_rate_limit(
			request,
			action="site_gate",
			limit=getattr(settings, "SITE_GATE_RATE_LIMIT", 10),
			window_seconds=getattr(settings, "SITE_GATE_RATE_WINDOW", 300),
			by_ip_only=True,
		)
		if not allowed:
			error = "Too many attempts. Please wait a few minutes and try again."
			return render(
				request,
				"sitepages/site_gate.html",
				{"error": error, "next": next_url, "is_site_gate": True},
			)
		submitted = (request.POST.get("password") or "").strip()
		expected = getattr(settings, "SITE_ACCESS_PASSWORD", "") or ""
		if expected and constant_time_compare(submitted, expected):
			request.session[SESSION_KEY] = True
			return redirect(_safe_next_url(next_url))
		error = "That password wasn't right. Please try again."

	return render(
		request,
		"sitepages/site_gate.html",
		{
			"error": error,
			"next": next_url,
			"is_site_gate": True,
		},
	)


def feedback(request):
	referrer = request.META.get("HTTP_REFERER") or ""
	# Prefer an explicit ?from= so footer links work even when Referer is stripped.
	previous = request.GET.get("from") or request.POST.get("previous_page") or referrer or ""
	feedback_type = (request.GET.get("type") or request.POST.get("feedback_type") or "").strip().lower()
	is_bug_report = feedback_type == "bug"

	if request.method == "POST":
		form = FeedbackForm(request.POST, is_bug_report=is_bug_report)
		if form.is_valid():
			submission = _store_feedback(form.cleaned_data, request, is_bug_report=is_bug_report)
			email_sent = _send_feedback_email(submission, is_bug_report=is_bug_report)
			if email_sent:
				submission.email_sent = True
				submission.save(update_fields=["email_sent"])
			request.session["feedback_want_reply"] = bool(submission.want_reply)
			return redirect("feedback_thanks")
	else:
		form = FeedbackForm(
			initial={"previous_page": previous},
			is_bug_report=is_bug_report,
		)

	return render(
		request,
		"sitepages/feedback.html",
		{
			"form": form,
			"previous_page": form["previous_page"].value() or previous,
			"is_bug_report": is_bug_report,
		},
	)


def feedback_thanks(request):
	want_reply = bool(request.session.pop("feedback_want_reply", False))
	return render(
		request,
		"sitepages/feedback_thanks.html",
		{"want_reply": want_reply},
	)


def _feedback_recipient() -> str:
	explicit = getattr(settings, "FEEDBACK_TO_EMAIL", None) or ""
	if explicit:
		return explicit
	admins = getattr(settings, "ADMINS", None) or []
	if admins:
		return admins[0][1]
	return getattr(settings, "DEFAULT_FROM_EMAIL", None) or "admin@localhost"


def _store_feedback(cleaned: dict, request, *, is_bug_report: bool = False) -> FeedbackSubmission:
	message = cleaned["message"].strip()
	if is_bug_report and not message.lower().startswith("[bug]"):
		message = f"[Bug] {message}"
	return FeedbackSubmission.objects.create(
		message=message,
		previous_page=(cleaned.get("previous_page") or "").strip()[:500],
		want_reply=bool(cleaned.get("want_reply")),
		reply_email=(cleaned.get("email") or "").strip(),
		user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
	)


def _send_feedback_email(submission: FeedbackSubmission, *, is_bug_report: bool = False) -> bool:
	from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or "noreply@localhost"
	to_email = _feedback_recipient()
	previous_page = submission.previous_page or "(not provided)"

	subject = "Bug report" if is_bug_report or submission.message.startswith("[Bug]") else "Site feedback"
	if submission.want_reply:
		subject += " (reply requested)"

	body_lines = [
		"New feedback from the site:",
		"",
		f"Submission id: {submission.pk}",
		f"Previous page: {previous_page}",
		f"Reply requested: {'yes' if submission.want_reply else 'no'}",
		f"Reply email: {submission.reply_email or '(none)'}",
		f"User agent: {submission.user_agent}",
		"",
		"Message:",
		submission.message,
		"",
		"Also saved on the server under Site pages → Feedback submissions.",
	]
	mail = EmailMessage(
		subject=subject,
		body="\n".join(body_lines),
		from_email=from_email,
		to=[to_email],
	)
	if submission.want_reply and submission.reply_email:
		mail.reply_to = [submission.reply_email]
	try:
		mail.send(fail_silently=False)
		return True
	except Exception:
		logger.exception("Failed to email feedback submission %s", submission.pk)
		return False
