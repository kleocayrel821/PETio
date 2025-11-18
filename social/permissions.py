"""
Permission helpers for the social app.

Provides lightweight helpers for checking moderator privileges that
mirror logic used by `ModeratorRequiredMixin`.
"""

from django.contrib.auth.models import Group


def is_moderator(user):
    """Return True if the user is a moderator or staff.

    A moderator is defined as a user in the 'Moderators' group or any
    user with `is_staff` set to True.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    return bool(user.is_staff or user.groups.filter(name='Moderators').exists())