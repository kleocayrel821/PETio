"""
Project-level context processors.

Provides:
- resolve_logout_url_name: picks the appropriate logout URL name based on configured routes.
"""
from django.urls import reverse, NoReverseMatch


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