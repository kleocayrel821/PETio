"""
Tests for moderation action views.

Covers:
- Dismissing a report unflags content when no other pending/reviewing reports exist.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

from social.models import Post, SocialReport, ModerationAction


User = get_user_model()


class DismissReportUnflagsTests(TestCase):
    """Dismiss report should close and unflag content without other pending reports."""

    def setUp(self):
        self.client = Client()
        self.moderator = User.objects.create_user(
            username='moderator', password='test123', is_staff=True
        )
        self.user = User.objects.create_user(username='author', password='test123')
        self.post = Post.objects.create(author=self.user, title='T', content='C', is_flagged=True, hidden_at=timezone.now())
        self.report = SocialReport.objects.create(
            reporter=self.moderator,
            reported_post=self.post,
            report_type='spam',
            description='Flagged for testing',
            status='pending',
        )

    def test_dismiss_unflags_post(self):
        self.client.login(username='moderator', password='test123')
        url = reverse('social:dismiss_report', kwargs={'pk': self.report.pk})
        response = self.client.post(url, {'reason': 'not spam'}, follow=True)
        self.assertEqual(response.status_code, 200)

        # Report is resolved
        self.report.refresh_from_db()
        self.assertEqual(self.report.status, 'resolved')

        # Post is unflagged since no other pending/reviewing reports exist
        self.post.refresh_from_db()
        self.assertFalse(self.post.is_flagged)
        self.assertIsNone(self.post.hidden_at)

        # Moderation action logged
        action = ModerationAction.objects.filter(related_report=self.report, action_type='dismiss_report').first()
        self.assertIsNotNone(action)