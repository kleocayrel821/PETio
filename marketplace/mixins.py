"""
Reusable permission mixin and decorator for Marketplace admin routes.

Usage (CBV):

    from django.views import View
    from marketplace.mixins import MarketplaceAdminPermRequiredMixin

    class ListingApprovalView(MarketplaceAdminPermRequiredMixin, View):
        required_permission = 'marketplace.can_approve_listing'
        # ... normal CBV methods

Usage (FBV):

    from marketplace.mixins import marketplace_admin_required

    @marketplace_admin_required(required_permission='marketplace.can_approve_listing')
    def admin_approve_listing(request, listing_id):
        # ... view logic

Notes:
- Unauthorized access raises `PermissionDenied` (HTTP 403).
- If `required_permission` is set, it must match the full permission string
  used by `user.has_perm()`, e.g. 'marketplace.can_approve_listing'.
"""

from functools import wraps
from typing import Optional, Callable

from django.core.exceptions import PermissionDenied


class MarketplaceAdminPermRequiredMixin:
    """CBV mixin that gates access to Marketplace admins.

    Conditions:
    - User must be authenticated.
    - User must be a superuser OR belong to the 'Marketplace Admin' group.
    - If the view defines `required_permission`, user must have that permission.
    """

    required_permission: Optional[str] = None

    def _is_marketplace_admin(self, user) -> bool:
        return user.is_superuser or user.groups.filter(name='Marketplace Admin').exists()

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if not user.is_authenticated:
            raise PermissionDenied("Authentication required")

        if not self._is_marketplace_admin(user):
            raise PermissionDenied("Marketplace admin access required")

        if self.required_permission and not user.has_perm(self.required_permission):
            raise PermissionDenied("Missing required permission")

        return super().dispatch(request, *args, **kwargs)


def marketplace_admin_required(view_func: Optional[Callable] = None, *, required_permission: Optional[str] = None):
    """Decorator for FBVs that gates access to Marketplace admins.

    Can be used with or without arguments:

        @marketplace_admin_required
        def my_view(request): ...

        @marketplace_admin_required(required_permission='marketplace.can_approve_listing')
        def my_view(request): ...
    """

    def decorator(func: Callable):
        @wraps(func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, 'user', None)

            if not user or not user.is_authenticated:
                raise PermissionDenied("Authentication required")

            if not (user.is_superuser or user.groups.filter(name='Marketplace Admin').exists()):
                raise PermissionDenied("Marketplace admin access required")

            if required_permission and not user.has_perm(required_permission):
                raise PermissionDenied("Missing required permission")

            return func(request, *args, **kwargs)

        return _wrapped

    if view_func is None:
        return decorator
    return decorator(view_func)