from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    priority = 1.0

    def items(self):
        return ["home", "about", "about_trainers", "how_to_gym", "feedback"]

    def location(self, item):
        return reverse(item)
