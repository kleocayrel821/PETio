"""
Context processors for the social app.

Adds global moderation-related context variables to templates for users
with moderator privileges, enabling badges and quick navigation.
"""

from .models import SocialReport
from .permissions import is_moderator


def moderation_context(request):
    """
    Add moderation-related context to all templates.

    Only active for authenticated moderators.
    Provides `is_moderator` and `pending_reports_count`.
    """
    if not request.user.is_authenticated:
        return {}

    if not is_moderator(request.user):
        return {}

    return {
        'is_moderator': True,
        'pending_reports_count': SocialReport.objects.filter(status='pending').count(),
    }