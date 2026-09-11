from io import BytesIO

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from apps.exercises.data_zoo import DATA_SCIENCE_SECTORS
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

        german = self.client.get(reverse("impressum"))
        self.assertEqual(german.status_code, 200)
        self.assertContains(german, "Impressum")


class UserProfileTests(TestCase):
    def test_profile_page_requires_authentication(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("home"))

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
            {"data_field": "biostatistics", "dataset_file": "01_diabetes.parquet"},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertRedirects(response, reverse("home"))
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.data_field, "biostatistics")
        self.assertEqual(user.profile.dataset_file, "01_diabetes.parquet")
        self.assertTrue(user.profile.onboarding_complete)

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
            "motivation": "I want to turn raw information into better decisions.",
            "photo": SimpleUploadedFile("avatar.png", image_bytes, content_type="image/png"),
        }

        response = self.client.post(reverse("profile"), payload)

        self.assertEqual(response.status_code, 302)
        self.assertTrue(UserProfile.objects.filter(user=user, nickname="DataNerd").exists())

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
            reverse("profile"),
            {
                "nickname": "DataNerd",
                "short_description": "Second profile",
                "motivation": "More learning.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This nickname is already in use.")
