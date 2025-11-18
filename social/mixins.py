"""Access control mixins for social app views.

Provides ModeratorRequiredMixin that ensures the requesting user is
authenticated and a member of the 'Moderators' group (or is staff).
"""

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin


class ModeratorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Mixin to restrict view access to moderators or staff users.

    Use this for Class-Based Views that represent moderation endpoints.
    The test allows users in the 'Moderators' group or `is_staff` users.
    """

    def test_func(self):
        user = self.request.user
        if not user.is_authenticated:
            return False
        return user.is_staff or user.groups.filter(name='Moderators').exists()