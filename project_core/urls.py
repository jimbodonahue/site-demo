"""
URL configuration for project_core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from .sitemap import StaticViewSitemap

sitemaps = {
    "static": StaticViewSitemap,
}

urlpatterns = [
    path("", TemplateView.as_view(template_name="home.html"), name="home"),
    path("admin/", admin.site.urls),
    path("exercises/", include("apps.exercises.urls")),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("accounts/", include("apps.authentication.urls")),
    path("metrics/", include(("apps.metrics.urls", "metrics"), namespace="metrics")),
    # path("env/", lambda request: JsonResponse(dict(os.environ))),
    path(
        "terms/",
        TemplateView.as_view(template_name="terms_of_services.html"),
        name="terms_of_service",
    ),
    path(
        "privacy/",
        TemplateView.as_view(template_name="privacy_policy.html"),
        name="privacy_policy",
    ),
    path(
        "cookies/",
        TemplateView.as_view(template_name="cookie_policy.html"),
        name="cookie_policy",
    ),
    path(
        "imprint/",
        TemplateView.as_view(template_name="imprint.html"),
        name="imprint",
    ),
    path(
        "impressum/",
        TemplateView.as_view(template_name="impressum.html"),
        name="impressum",
    ),
    path(
        "robots.txt",
        TemplateView.as_view(
            template_name="robots.txt",
            content_type="text/plain",
        ),
    ),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
