"""
Accounts models: Custom User and Profile.
- User extends AbstractUser to allow richer user information gathering.
- Profile holds optional, user-facing fields.
"""
from django.db import models
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import AbstractUser

class User(AbstractUser):
    """Custom user model based on Django's AbstractUser.

    Adds fields to support collecting more information and future features.
    """
    # Make email unique for reliable contact and activation flows.
    email = models.EmailField("email address", unique=True, blank=True)
    # Optional contact and demographic info
    mobile_number = models.CharField(max_length=32, blank=True, help_text="E.164 format, e.g., +1 555 123 4567")
    age = models.PositiveIntegerField(blank=True, null=True, help_text="Age in years")
    marketing_opt_in = models.BooleanField(default=False, help_text="User agreed to receive marketing updates")

    class Meta:
        ordering = ["username"]

    def __str__(self) -> str:
        """Return a human-readable representation of the user."""
        return f"User({self.username})"

class Profile(models.Model):
    """User profile linked 1:1 with the custom User model.

    Add optional fields to support marketplace and feeder features.
    """
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    display_name = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    location = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to='avatars/%Y/%m/', blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['user__username']

    def __str__(self) -> str:
        """Return a human-readable representation of the profile."""
        return f"Profile({self.user.username})"