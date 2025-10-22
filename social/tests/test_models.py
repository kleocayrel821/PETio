from django.test import TestCase
from django.contrib.auth import get_user_model
from social.models import Category, Post, Comment, Like, Follow, Announcement, Notification, UserProfile


User = get_user_model()


class ModelStructureTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        self.category = Category.objects.create(name='General')

    def test_profile_created_and_fields(self):
        profile = UserProfile.objects.create(user=self.user1, bio='Hello')
        self.assertEqual(profile.user, self.user1)
        self.assertEqual(profile.bio, 'Hello')

    def test_post_creation(self):
        post = Post.objects.create(author=self.user1, title='T', content='C', category=self.category)
        self.assertEqual(post.author, self.user1)
        self.assertEqual(post.title, 'T')
        self.assertEqual(post.category, self.category)

    def test_comment_creation(self):
        post = Post.objects.create(author=self.user1, title='T', content='C')
        comment = Comment.objects.create(post=post, author=self.user2, content='Nice')
        self.assertEqual(comment.post, post)
        self.assertEqual(comment.author, self.user2)

    def test_like_unique_together(self):
        post = Post.objects.create(author=self.user1, title='T', content='C')
        Like.objects.create(post=post, user=self.user2)
        with self.assertRaises(Exception):
            Like.objects.create(post=post, user=self.user2)

    def test_follow_unique_together(self):
        Follow.objects.create(follower=self.user1, following=self.user2)
        with self.assertRaises(Exception):
            Follow.objects.create(follower=self.user1, following=self.user2)

    def test_announcement(self):
        ann = Announcement.objects.create(title='Hello', content='World', active=True)
        self.assertTrue(ann.active)
        self.assertEqual(str(ann), 'Hello')

    def test_notification(self):
        post = Post.objects.create(author=self.user1, title='T', content='C')
        notif = Notification.objects.create(
            recipient=self.user2,
            sender=self.user1,
            type=Notification.LIKE,
            post=post,
            message='liked your post',
        )
        self.assertFalse(notif.read)
        self.assertIn('liked your post', notif.message)