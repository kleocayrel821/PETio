from django.test import TestCase
from django.contrib.auth import get_user_model
from social.forms import PostForm, CommentForm, ProfileForm
from social.models import Category


User = get_user_model()


class FormValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='user', password='pass')
        self.category = Category.objects.create(name='General')

    def test_post_form_valid(self):
        form = PostForm(data={'title': 'Hello', 'content': 'World', 'category': self.category.id})
        self.assertTrue(form.is_valid())

    def test_post_form_invalid_without_title(self):
        form = PostForm(data={'title': '', 'content': 'World'})
        self.assertFalse(form.is_valid())

    def test_comment_form_valid(self):
        form = CommentForm(data={'content': 'Nice post'})
        self.assertTrue(form.is_valid())

    def test_profile_form_valid(self):
        form = ProfileForm(data={'bio': 'About me'})
        self.assertTrue(form.is_valid())