from django.test import SimpleTestCase


class CoursesRetiredTests(SimpleTestCase):
	def test_courses_urls_are_not_mounted(self):
		from django.urls import NoReverseMatch, reverse

		with self.assertRaises(NoReverseMatch):
			reverse("courses:list")
