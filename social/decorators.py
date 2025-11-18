"""Access control decorators for social moderation endpoints.

Defines `moderator_required` and `admin_required` decorators to protect
Function-Based Views. Moderators are identified by membership in the
`Moderators` group; admins use `is_staff`.
"""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.contrib import messages


def _is_moderator(user):
    """Return True if user is a moderator or staff."""
    return user.is_authenticated and (
        user.is_staff or user.groups.filter(name='Moderators').exists()
    )


def moderator_required(view_func):
    """Decorator to restrict access to moderators or staff users.

    Non-authorized users are redirected to the social dashboard with an
    error message.
    """

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not _is_moderator(request.user):
            messages.error(request, 'You must be a moderator to access this page.')
            return redirect('social:dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped


def admin_required(view_func):
    """Decorator to restrict access to staff/admin users.

    Non-authorized users are redirected to the social dashboard with an
    error message.
    """

    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            messages.error(request, 'You must be an admin to access this page.')
            return redirect('social:dashboard')
        return view_func(request, *args, **kwargs)

    return _wrapped