"""
Django signals to auto-create and save Profile objects on User creation and update.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import Profile

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