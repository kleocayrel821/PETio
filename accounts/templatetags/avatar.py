from django import template
from django.contrib.auth.models import AnonymousUser
from django.utils.html import escape

register = template.Library()


def _name_for(user):
    try:
        full = getattr(user, 'get_full_name', lambda: '')()
        if full:
            return full
        return getattr(user, 'username', '') or 'User'
    except Exception:
        return 'User'


@register.simple_tag
def avatar_url(user=None, size=64, bg="3B82F6", color="fff"):
    """Return a URL to the user's avatar image.

    Prefers Profile.avatar if available; falls back to UI Avatars with the user's name.
    If user is None or anonymous, returns a generic placeholder avatar.
    """
    try:
        if not user or isinstance(user, AnonymousUser) or not getattr(user, 'is_authenticated', False):
            # Generic placeholder (uses UI Avatars 'Guest')
            return f"https://ui-avatars.com/api/?name=Guest&size={int(size)}&background={bg}&color={color}"

        profile = getattr(user, 'profile', None)
        # If profile exists and has an uploaded avatar, use it
        if profile and getattr(profile, 'avatar', None) and getattr(profile.avatar, 'url', None):
            return profile.avatar.url

        # Fallback to UI Avatars using the user's name
        name = escape(_name_for(user))
        return f"https://ui-avatars.com/api/?name={name}&size={int(size)}&background={bg}&color={color}"
    except Exception:
        # Final fallback to an app static placeholder if something goes wrong
        return f"https://ui-avatars.com/api/?name=User&size={int(size)}&background={bg}&color={color}"