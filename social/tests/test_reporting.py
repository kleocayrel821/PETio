"""
Tests for moderation reporting functionality and context.

Covers:
- Reports list access and filtering for moderators
- Report detail view loads and auto-transition to 'reviewing'
- Global context processor exposes moderator badge with pending count
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

from social.models import Post, Comment, SocialReport, Category


User = get_user_model()


class ReportListTests(TestCase):
    """Test report listing and filtering."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            username='moderator', password='test123', is_staff=True
        )
        self.user = User.objects.create_user(username='testuser', password='test123')

        # Create test post and report
        self.post = Post.objects.create(author=self.user, title='Test', content='Content')
        self.report = SocialReport.objects.create(
            reporter=self.moderator,
            reported_post=self.post,
            reported_user=self.user,
            report_type='spam',
            description='Test report',
            status='pending',
        )

    def test_moderator_can_access_reports(self):
        """Moderators can access the reports list."""
        self.client.login(username='moderator', password='test123')
        url = reverse('social:moderation_reports')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'reports')

    def test_regular_user_cannot_access_reports(self):
        """Regular users cannot access moderation pages."""
        self.client.login(username='testuser', password='test123')
        url = reverse('social:moderation_reports')
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])

    def test_report_filtering_by_status(self):
        """Filtering works by status=pending."""
        self.client.login(username='moderator', password='test123')
        url = reverse('social:moderation_reports')
        response = self.client.get(url, {'status': 'pending'})
        self.assertEqual(response.status_code, 200)
        # The pending report should appear with type badge
        self.assertContains(response, 'Spam')


class ReportDetailTests(TestCase):
    """Test report detail view behavior."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            username='moderator', password='test123', is_staff=True
        )
        self.user = User.objects.create_user(username='testuser', password='test123')

        self.post = Post.objects.create(author=self.user, title='Test Post', content='Content')
        self.report = SocialReport.objects.create(
            reporter=self.moderator,
            reported_post=self.post,
            reported_user=self.user,
            report_type='spam',
            description='Detailed test report',
            status='pending',
        )

    def test_report_detail_loads_and_sets_reviewing(self):
        """Viewing a pending report changes its status to reviewing."""
        self.client.login(username='moderator', password='test123')
        url = reverse('social:report_detail', kwargs={'pk': self.report.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Status should now be 'reviewing'
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'reviewing')


class ModerationContextProcessorTests(TestCase):
    """Test global moderation context processor injection."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            username='moderator', password='test123', is_staff=True
        )
        self.user = User.objects.create_user(username='testuser', password='test123')
        # Create a pending report to ensure count >= 1
        SocialReport.objects.create(
            reporter=self.moderator,
            reported_user=self.user,
            report_type='harassment',
            description='Pending moderation',
            status='pending',
        )

    def test_feed_shows_moderation_button_for_moderator(self):
        """Feed includes badge/button when user is a moderator."""
        self.client.login(username='moderator', password='test123')
        url = reverse('social:feed')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Link to moderation dashboard should be present
        self.assertContains(response, reverse('social:moderation_dashboard'))