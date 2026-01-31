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
            return f"https://ui-avatars.com/api/?name=Guest&size={int(size)}&background={bg}&color={color}"

        for rel in ('social_profile', 'marketplace_profile', 'profile'):
            p = getattr(user, rel, None)
            if p and getattr(p, 'avatar', None) and getattr(p.avatar, 'url', None):
                url = p.avatar.url
                if url.startswith('http://'):
                    url = 'https://' + url[len('http://'):]
                if url.startswith('/'):
                    continue
                return url

        name = escape(_name_for(user))
        return f"https://ui-avatars.com/api/?name={name}&size={int(size)}&background={bg}&color={color}"
    except Exception:
        return f"https://ui-avatars.com/api/?name=User&size={int(size)}&background={bg}&color={color}"
