"""Unit tests for accounts app Profile model and signal behavior."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from .models import Profile
from django.urls import reverse
from django.test import Client
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.files.uploadedfile import SimpleUploadedFile

User = get_user_model()


class ProfileModelTests(TestCase):
    """Ensure Profile is created/updated alongside User via signals."""

    def test_profile_created_on_user_creation(self):
        user = User.objects.create_user(username="alice", email="alice@example.com", password="secret123")
        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_profile_saves_with_user(self):
        user = User.objects.create_user(username="bob", email="bob@example.com", password="secret123")
        profile = user.profile
        profile.bio = "I love pets!"
        profile.save()
        self.assertEqual(Profile.objects.get(user=user).bio, "I love pets!")


class TestRegistrationActivation(TestCase):
    """Signup creates inactive user; activation link activates the user."""

    def setUp(self):
        self.client = Client()

    def test_signup_creates_inactive_and_activation_works(self):
        signup_url = reverse("accounts:signup")
        data = {
            "username": "newuser",
            "password1": "StrongPass!234",
            "password2": "StrongPass!234",
            "email": "newuser@example.com",
        }
        resp = self.client.post(signup_url, data=data)
        # Should redirect to login page after signup
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.headers.get("Location", ""))

        # User should be created and inactive
        user = User.objects.get(username="newuser")
        self.assertFalse(user.is_active)

        # Simulate clicking activation link
        uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        activate_url = reverse("accounts:activate", kwargs={"uidb64": uidb64, "token": token})
        resp2 = self.client.get(activate_url)
        self.assertEqual(resp2.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)


class TestLoginLogoutFlows(TestCase):
    """Verify login and logout views operate correctly with redirects and session state."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="loginuser", email="login@example.com", password="pass1234")
        self.user.is_active = True
        self.user.save()

    def test_login_success_and_profile_access_then_logout(self):
        # Login via built-in auth view
        resp = self.client.post(reverse("login"), data={"username": "loginuser", "password": "pass1234"})
        self.assertEqual(resp.status_code, 302)
        # After login, profile (login-required) should be accessible
        prof_resp = self.client.get(reverse("accounts:profile"))
        self.assertEqual(prof_resp.status_code, 200)
        # Now logout (Django 5 requires POST for LogoutView)
        self.client.post(reverse("logout"))
        # Depending on settings, logout may redirect or render a page; ensure not authenticated anymore
        prof_redirect = self.client.get(reverse("accounts:profile"))
        self.assertEqual(prof_redirect.status_code, 302)
        self.assertIn(reverse("login"), prof_redirect.headers.get("Location", ""))


class TestPasswordResetChange(TestCase):
    """End-to-end tests for password reset and password change flows."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="resetuser", email="reset@example.com", password="origPass!234")
        self.user.is_active = True
        self.user.save()

    def test_password_reset_flow(self):
        # Request password reset
        resp = self.client.post(reverse("password_reset"), data={"email": "reset@example.com"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("password_reset_done"), resp.headers.get("Location", ""))
        # Email should be sent (Django test backend captures in outbox)
        self.assertGreaterEqual(len(mail.outbox), 1)

        # Extract password reset URL from the sent email to ensure a valid token
        reset_email = mail.outbox[-1]
        import re
        match = re.search(r"http://testserver[\S]*/reset/[^/]+/[^/]+/", reset_email.body)
        self.assertIsNotNone(match, "Password reset URL not found in email body")
        confirm_url = match.group(0).replace("http://testserver", "")

        # Django 5 PasswordResetConfirmView redirects token URL to 'set-password/'
        # Follow the redirect so session token is established; capture final path
        resp2 = self.client.get(confirm_url, follow=True)
        self.assertEqual(resp2.status_code, 200)
        set_password_url = resp2.wsgi_request.path

        # Post new password to the set-password URL
        new_pw = "NewSecurePass!789"
        resp3 = self.client.post(set_password_url, data={
            "new_password1": new_pw,
            "new_password2": new_pw,
        })
        self.assertEqual(resp3.status_code, 302)
        self.assertIn(reverse("password_reset_complete"), resp3.headers.get("Location", ""))

        # Can log in with new password
        login_ok = self.client.login(username="resetuser", password=new_pw)
        self.assertTrue(login_ok)

    def test_password_change_flow(self):
        # Login first
        self.assertTrue(self.client.login(username="resetuser", password="origPass!234"))
        # Change password
        change_resp = self.client.post(reverse("password_change"), data={
            "old_password": "origPass!234",
            "new_password1": "AnotherNew!123",
            "new_password2": "AnotherNew!123",
        })
        self.assertEqual(change_resp.status_code, 302)
        self.assertIn(reverse("password_change_done"), change_resp.headers.get("Location", ""))
        # Logout and login with new password (Django 5 requires POST)
        self.client.post(reverse("logout"))
        self.assertTrue(self.client.login(username="resetuser", password="AnotherNew!123"))


class TestProfileEditView(TestCase):
    """Tests for the ProfileUpdateView: authentication and update behavior."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username="edith", email="edith@example.com", password="Pass!23456")
        self.user.is_active = True
        self.user.save()
        self.url = reverse("accounts:profile_edit")

    def test_login_required(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("login"), resp.headers.get("Location", ""))

    def test_get_renders_form(self):
        self.assertTrue(self.client.login(username="edith", password="Pass!23456"))
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "accounts/profile_edit.html")

    def test_post_updates_profile(self):
        self.assertTrue(self.client.login(username="edith", password="Pass!23456"))
        data = {
            "display_name": "Edith",
            "bio": "Pet parent",
            "location": "NYC",
            "phone": "123-456",
        }
        resp = self.client.post(self.url, data=data)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:profile"), resp.headers.get("Location", ""))
        prof = self.user.profile
        prof.refresh_from_db()
        self.assertEqual(prof.display_name, "Edith")
        self.assertEqual(prof.bio, "Pet parent")
        self.assertEqual(prof.location, "NYC")
        self.assertEqual(prof.phone, "123-456")

    def test_avatar_size_validation(self):
        self.assertTrue(self.client.login(username="edith", password="Pass!23456"))
        # Create an oversized valid BMP image (>5MB) to ensure Pillow validates it as an image
        from PIL import Image
        import io
        img = Image.new("RGB", (2000, 2000), color=(255, 255, 255))  # ~12MB as BMP
        buf = io.BytesIO()
        img.save(buf, format="BMP")
        big_content = buf.getvalue()
        self.assertGreater(len(big_content), 5 * 1024 * 1024)
        big_file = SimpleUploadedFile("avatar.bmp", big_content, content_type="image/bmp")
        data = {
            "display_name": "Edith",
            "bio": "Pet parent",
            "location": "NYC",
            "phone": "123-456",
            "avatar": big_file,
        }
        resp = self.client.post(self.url, data=data, follow=True)
        # Stay on the form page with validation errors
        self.assertEqual(resp.status_code, 200)
        self.assertTemplateUsed(resp, "accounts/profile_edit.html")
        # Assert the avatar field error is present on the bound form instance
        form = resp.context["form"]
        self.assertFormError(form, "avatar", "Avatar file too large. Max size is 5MB.")