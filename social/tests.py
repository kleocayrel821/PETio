"""Minimal unit tests for social wireframe views.

These tests ensure the wireframe pages are reachable and render the expected templates.
"""
from django.test import TestCase
from django.urls import reverse


class SocialWireframeViewsTests(TestCase):
    """Tests for social feed, friends, messages, notifications, profile, and forum views."""

    def test_feed_view(self):
        url = reverse('social:feed')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/feed.html')

    def test_friends_view(self):
        url = reverse('social:friends')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/friends.html')

    # Messages feature removed; corresponding test deleted.

    def test_notifications_view(self):
        url = reverse('social:notifications')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/notifications.html')

    def test_profile_view(self):
        url = reverse('social:profile')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/profile.html')

    def test_forum_categories_view(self):
        url = reverse('social:forum_categories')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/forum_categories.html')

    def test_forum_threads_view(self):
        url = reverse('social:forum_threads', kwargs={'category_slug': 'general'})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/forum_threads.html')
        # Ensure context contains category_name derived from slug
        self.assertIn('category_name', resp.context)
        self.assertEqual(resp.context['category_name'], 'General')

    def test_new_thread_view(self):
        url = reverse('social:new_thread')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/new_thread.html')
        self.assertIn('categories', resp.context)

    def test_thread_detail_view(self):
        url = reverse('social:thread_detail', kwargs={'thread_id': 42})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, 'social/thread_detail.html')
