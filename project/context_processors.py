"""
Project-level context processors.

Provides:
- resolve_logout_url_name: picks the appropriate logout URL name based on configured routes.
"""
from django.urls import reverse, NoReverseMatch
from django.contrib.auth.models import AnonymousUser
try:
    from social.models import Notification as SocialNotification
except Exception:
    SocialNotification = None
try:
    from marketplace.models import Notification as MarketplaceNotification
except Exception:
    MarketplaceNotification = None
try:
    from controller.models import Hardware as ControllerHardware
except Exception:
    ControllerHardware = None
from django.conf import settings

def device_id_context(request):
    """Expose DEVICE_ID to templates for dynamic UI references."""
    return {"DEVICE_ID": getattr(settings, 'DEVICE_ID', 'feeder-1')}


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


def app_context(request):
    """
    Detect which app the user is in based on URL path and
    provide contextual variables for templates (navbar, sidebar).

    Falls back to PETio platform defaults when at root or unknown paths.
    """
    path = request.path or ""

    if path.startswith('/marketplace/'):
        return {
            'current_app': 'marketplace',
            'current_app_name': 'Marketplace',
            'current_app_icon': '🛒',
            'current_app_description': 'Products & Services',
        }
    if path.startswith('/social/'):
        return {
            'current_app': 'social',
            'current_app_name': 'Social',
            'current_app_icon': '👥',
            'current_app_description': 'Community & Sharing',
        }
    # Controller lives at site root ("/") and under controller-specific paths
    if path.startswith('/controller/') or path == '/' or path.startswith('/schedules') or path.startswith('/history'):
        return {
            'current_app': 'controller',
            'current_app_name': 'Controller',
            'current_app_icon': '🎮',
            'current_app_description': 'Feed & Schedule Management',
        }

    return {
        'current_app': None,
        'current_app_name': 'PETio',
        'current_app_icon': '🐾',
        'current_app_description': 'Pet Care Platform',
    }


def unread_notifications_count(request):
    """Provide unread notifications count for the navbar badge.

    Returns 0 if user is anonymous or notifications app/model is unavailable.
    """
    user = getattr(request, 'user', None)
    if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {"unread_notifications_count": 0}
    path = request.path or ""
    count = 0
    if path.startswith("/social/"):
        try:
            if SocialNotification is not None:
                count = SocialNotification.objects.filter(recipient=user, is_read=False).count()
        except Exception:
            count = 0
    elif path.startswith("/marketplace/"):
        try:
            if MarketplaceNotification is not None:
                count = MarketplaceNotification.objects.filter(user=user, read_at__isnull=True).count()
        except Exception:
            count = 0
    return {"unread_notifications_count": count}


def controller_has_devices(request):
    user = getattr(request, "user", None)
    if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return {"controller_has_devices": False}
    if ControllerHardware is None:
        return {"controller_has_devices": False}
    try:
        has_devices = ControllerHardware.objects.filter(paired_user=user, is_paired=True).exists()
        return {"controller_has_devices": has_devices}
    except Exception:
        return {"controller_has_devices": False}
