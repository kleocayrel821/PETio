"""
Django signals to auto-create and save Profile objects on User creation and update.
"""
from django.db.models.signals import post_save, post_migrate
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile
import os

User = get_user_model()

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create a Profile when a new User is created.

    Use get_or_create to avoid unique constraint errors if another signal/action
    attempts to create the profile concurrently.
    """
    if created:
        Profile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, created=False, **kwargs):
    """Ensure profile is saved when User is saved (if it exists).

    Avoid creating a Profile on the same 'created' signal dispatch to prevent
    race conditions leading to duplicate creations.
    """
    if created:
        # Profile creation handled in create_user_profile; skip here.
        return
    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.get_or_create(user=instance)


@receiver(post_migrate)
def ensure_superuser(sender, **kwargs):
    try:
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if username and email and password:
            if not User.objects.filter(username=username).exists():
                User.objects.create_superuser(username=username, email=email, password=password)
    except Exception:
        pass
