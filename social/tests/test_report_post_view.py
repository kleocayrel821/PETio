"""
Tests for the user-facing post reporting flow.

Covers:
- Access control for the report view
- Successful report submission flags post and persists SocialReport
- Authors cannot report their own posts
- Invalid form submission returns errors
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from social.models import Post, SocialReport


User = get_user_model()


class ReportPostViewTests(TestCase):
    """Verify behavior of the `report_post` view."""

    def setUp(self):
        self.client = Client()
        self.author = User.objects.create_user(username="author", password="pass123")
        self.reporter = User.objects.create_user(username="reporter", password="pass123")
        self.post = Post.objects.create(author=self.author, title="Hello", content="World content")

    def test_requires_login(self):
        """Anonymous users are redirected to login when visiting report page."""
        url = reverse("social:report_post", kwargs={"pk": self.post.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_get_form_as_non_author(self):
        """Logged-in non-author can load the report form."""
        self.client.login(username="reporter", password="pass123")
        url = reverse("social:report_post", kwargs={"pk": self.post.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report Post")

    def test_successful_report_submission_flags_post(self):
        """Submitting a valid report creates SocialReport and flags the post."""
        self.client.login(username="reporter", password="pass123")
        url = reverse("social:report_post", kwargs={"pk": self.post.pk})
        payload = {
            "report_type": "harassment",
            "description": "Rude content",
        }
        response = self.client.post(url, data=payload, follow=True)
        self.assertEqual(response.status_code, 200)
        # One report created linking reporter and post
        self.assertEqual(SocialReport.objects.count(), 1)
        report = SocialReport.objects.first()
        self.assertEqual(report.reporter, self.reporter)
        self.assertEqual(report.reported_post, self.post)
        # Post should be flagged
        self.post.refresh_from_db()
        self.assertTrue(self.post.is_flagged)

    def test_author_cannot_report_own_post(self):
        """Authors are redirected back to post detail and no report is created."""
        self.client.login(username="author", password="pass123")
        url = reverse("social:report_post", kwargs={"pk": self.post.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SocialReport.objects.count(), 0)

    def test_invalid_form_submission(self):
        """Missing report_type keeps user on form and shows errors."""
        self.client.login(username="reporter", password="pass123")
        url = reverse("social:report_post", kwargs={"pk": self.post.pk})
        payload = {
            "description": "No type provided",
        }
        response = self.client.post(url, data=payload)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Please fix the errors")
        self.assertEqual(SocialReport.objects.count(), 0)