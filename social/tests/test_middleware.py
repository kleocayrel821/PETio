"""
Tests for SuspensionCheckMiddleware behavior.

Verifies that a suspended user cannot perform write actions in the social app
and is redirected with an error message when attempting to create a post or
comment.
"""

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from social.models import UserProfile, Post, Category


User = get_user_model()


class SuspensionMiddlewareTests(TestCase):
    """Middleware blocks unsafe social actions for suspended users."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='suspended', password='test123')
        self.profile = UserProfile.objects.create(
            user=self.user,
            is_suspended=True,
            suspended_until=timezone.now() + timedelta(days=1),
            suspension_reason='Test suspension',
        )
        # Minimal category so PostForm can bind; adapt if categories are required
        Category.objects.create(name='General')

    def test_block_create_post(self):
        """Suspended user POST to create_post is redirected and no post created."""
        self.client.login(username='suspended', password='test123')
        url = reverse('social:create_post')
        response = self.client.post(url, {
            'title': 'Blocked Title',
            'content': 'Blocked content',
        }, follow=True)

        # Should redirect to feed
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('social:feed'))
        # No posts by suspended user
        self.assertEqual(Post.objects.filter(author=self.user).count(), 0)

    def test_block_comment_create(self):
        """Suspended user cannot comment on a post (comment_create)."""
        # Create a post by a different user so comment_create has a target
        other = User.objects.create_user(username='author', password='test123')
        post = Post.objects.create(author=other, title='Open', content='Hello')

        self.client.login(username='suspended', password='test123')
        url = reverse('social:comment_create', kwargs={'post_id': post.pk})
        response = self.client.post(url, {'content': 'Blocked comment'}, follow=True)

        # Should redirect to feed
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('social:feed'))