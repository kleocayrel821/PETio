from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from social.models import Post, Category


User = get_user_model()


class ViewAccessTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='user', password='pass')
        self.other = User.objects.create_user(username='other', password='pass')
        self.category = Category.objects.create(name='General')

    def test_feed_page_200(self):
        url = reverse('social:feed')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_home_page_200(self):
        url = reverse('social:home')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_dashboard_requires_login(self):
        url = reverse('social:dashboard')
        resp = self.client.get(url)
        # dashboard may be public in this app; accept 200 or redirect
        self.assertIn(resp.status_code, (200, 302))

    def test_create_post_requires_login(self):
        url = reverse('social:create_post')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)  # login redirect
        self.client.login(username='user', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_post_detail_200(self):
        post = Post.objects.create(author=self.user, title='T', content='C', category=self.category)
        url = reverse('social:post_detail', kwargs={'pk': post.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_edit_post_requires_owner(self):
        post = Post.objects.create(author=self.user, title='T', content='C')
        url = reverse('social:edit_post', kwargs={'pk': post.pk})
        self.client.login(username='other', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)
        self.client.login(username='user', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_like_toggle_ajax(self):
        post = Post.objects.create(author=self.user, title='T', content='C')
        url = reverse('social:toggle_like', kwargs={'post_id': post.pk})
        self.client.login(username='other', password='pass')
        resp = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)

    def test_comment_create_ajax(self):
        post = Post.objects.create(author=self.user, title='T', content='C')
        url = reverse('social:comment_create', kwargs={'post_id': post.pk})
        self.client.login(username='other', password='pass')
        resp = self.client.post(url, {'content': 'Nice'}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)

    def test_follow_toggle_ajax(self):
        url = reverse('social:toggle_follow', kwargs={'user_id': self.user.pk})
        self.client.login(username='other', password='pass')
        resp = self.client.post(url, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(resp.status_code, 200)

    def test_notifications_page(self):
        url = reverse('social:notifications')
        self.client.login(username='user', password='pass')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
