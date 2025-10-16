"""
Project-level context processors.

Provides:
- resolve_logout_url_name: picks the appropriate logout URL name based on configured routes.
"""
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.models import AnonymousUser
try:
    from social.models import Notification
except Exception:
    Notification = None


def resolve_logout_url_name(request):
    """Return context var 'logout_url_name' selecting accounts:logout if present, else logout.

    This makes the templates resilient across setups that use Django's built-in auth URLs
    or a custom accounts app with namespacing.
    """
    # Prefer namespaced accounts logout if present
    try:
        reverse("accounts:logout")
        return {"logout_url_name": "accounts:logout"}
    except NoReverseMatch:
        pass

    # Fallback to built-in auth logout
    try:
        reverse("logout")
        return {"logout_url_name": "logout"}
    except NoReverseMatch:
        # No known logout route; omit the link
        return {"logout_url_name": None}


def unread_notifications_count(request):
    """Provide unread notifications count for the navbar badge.

    Returns 0 if user is anonymous or notifications app/model is unavailable.
    """
    user = getattr(request, 'user', None)
    if Notification is None or not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {"unread_notifications_count": 0}
    try:
        count = Notification.objects.filter(recipient=user, is_read=False).count()
    except Exception:
        count = 0
    return {"unread_notifications_count": count}