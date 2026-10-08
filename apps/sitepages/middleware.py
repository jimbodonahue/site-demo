from urllib.parse import urlencode

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


SESSION_KEY = "site_access_granted"


class SiteAccessMiddleware:
	"""Require a shared site password once per session before browsing."""

	def __init__(self, get_response):
		self.get_response = get_response

	def __call__(self, request):
		password = getattr(settings, "SITE_ACCESS_PASSWORD", "") or ""
		if not password:
			return self.get_response(request)

		if request.session.get(SESSION_KEY):
			return self.get_response(request)

		path = request.path
		if self._is_exempt(path):
			return self.get_response(request)

		gate_url = reverse("site_gate")
		query = urlencode({"next": path})
		return redirect(f"{gate_url}?{query}")

	def _is_exempt(self, path: str) -> bool:
		# Static assets, admin, and legal/cookie pages stay reachable so the
		# gate landing page can show the same consent banner and policy links.
		exempt_prefixes = (
			"/static/",
			"/media/",
			"/admin/",
			"/metrics/",
			"/robots.txt",
			"/sitemap.xml",
			"/privacy/",
			"/cookies/",
			"/terms/",
			"/imprint/",
			"/impressum/",
		)
		if any(path.startswith(prefix) for prefix in exempt_prefixes):
			return True
		gate_path = reverse("site_gate")
		return path == gate_path or path.rstrip("/") == gate_path.rstrip("/")
