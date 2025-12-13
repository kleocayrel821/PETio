"""Class-Based Views for social moderation endpoints.

Includes dashboard, report list/detail, logs, queue, and user management.
Access is restricted via ModeratorRequiredMixin.
"""

from datetime import timedelta
from django.utils import timezone
from django.db.models import Count
from django.views.generic import TemplateView, ListView, DetailView

from .mixins import ModeratorRequiredMixin
from .models import (
    Post,
    Comment,
    UserProfile,
    SocialReport,
    ModerationAction,
)
from .views import get_moderation_context


class ModerationDashboardView(ModeratorRequiredMixin, TemplateView):
    """Moderation dashboard with stats and recent activity."""
    template_name = 'social/moderation/dashboard.html'

    def get_context_data(self, **kwargs):
        """Build dashboard context including counts and recent items."""
        context = super().get_context_data(**kwargs)
        # Counts
        context['pending_reports_count'] = SocialReport.objects.filter(status='pending').count()
        context['reviewing_reports_count'] = SocialReport.objects.filter(status='reviewing').count()
        context['flagged_posts_count'] = Post.objects.filter(is_flagged=True).count()
        context['flagged_comments_count'] = Comment.objects.filter(is_flagged=True).count()
        context['suspended_users_count'] = UserProfile.objects.filter(is_suspended=True).count()

        days = 7
        try:
            d = int(self.request.GET.get('range', 7))
            if d in (7, 30, 90):
                days = d
        except Exception:
            pass
        week_ago = timezone.now() - timedelta(days=days)
        context['weekly_stats'] = {
            'reports_created': SocialReport.objects.filter(created_at__gte=week_ago).count(),
            'reports_resolved': SocialReport.objects.filter(status='resolved', updated_at__gte=week_ago).count(),
            'actions_taken': ModerationAction.objects.filter(created_at__gte=week_ago).count(),
            'users_suspended': UserProfile.objects.filter(is_suspended=True, updated_at__gte=week_ago).count(),
        }
        context['range_days'] = days

        # Recent items
        context['recent_reports'] = SocialReport.objects.select_related('reporter', 'reported_user').order_by('-created_at')[:8]
        context['recent_actions'] = ModerationAction.objects.select_related('moderator', 'target_user').order_by('-created_at')[:12]

        # Moderator stats for current user
        if self.request.user.is_authenticated:
            thirty_days_ago = timezone.now() - timedelta(days=30)
            qs = ModerationAction.objects.filter(moderator=self.request.user, created_at__gte=thirty_days_ago)
            # Aggregate counts by action_type
            agg = qs.values('action_type').annotate(count=Count('id')).order_by('-count')
            context['moderator_stats'] = list(agg)
            context['user_actions_count'] = ModerationAction.objects.filter(moderator=self.request.user).count()
        else:
            context['moderator_stats'] = []
            context['user_actions_count'] = 0
        # Add unified moderation context (counts, flags)
        context.update(get_moderation_context(self.request))
        return context


class ModerationReportsView(ModeratorRequiredMixin, ListView):
    """List of reports with optional status filtering."""
    template_name = 'social/moderation/reports.html'
    context_object_name = 'reports'
    paginate_by = 20

    def get_queryset(self):
        status = self.request.GET.get('status')
        qs = SocialReport.objects.select_related('reporter', 'reported_user').order_by('-created_at')
        if status in {'pending', 'reviewing', 'resolved'}:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        """Inject moderation sidebar/context counts into reports list."""
        context = super().get_context_data(**kwargs)
        context.update(get_moderation_context(self.request))
        return context


class ReportDetailView(ModeratorRequiredMixin, DetailView):
    """Detail view for a single report."""
    template_name = 'social/moderation/report_detail.html'
    context_object_name = 'report'
    queryset = SocialReport.objects.select_related('reporter', 'reported_user')

    def get_context_data(self, **kwargs):
        """Add moderation context to detail view for sidebar badges."""
        context = super().get_context_data(**kwargs)
        context.update(get_moderation_context(self.request))
        return context

    def get(self, request, *args, **kwargs):
        """On view, auto-transition pending reports to 'reviewing'."""
        # Fetch the report instance
        report = self.get_object()
        if report.status == 'pending':
            report.status = 'reviewing'
            report.save(update_fields=['status', 'updated_at'])
        # Continue with normal detail rendering
        return super().get(request, *args, **kwargs)


class ModerationLogsView(ModeratorRequiredMixin, ListView):
    """Recent moderation actions log."""
    template_name = 'social/moderation/logs.html'
    context_object_name = 'actions'
    paginate_by = 30

    def get_queryset(self):
        return ModerationAction.objects.select_related('moderator', 'target_user').order_by('-created_at')

    def get_context_data(self, **kwargs):
        """Add moderation context to logs view."""
        context = super().get_context_data(**kwargs)
        context.update(get_moderation_context(self.request))
        return context


class ModerationQueueView(ModeratorRequiredMixin, TemplateView):
    """Queue of flagged posts and comments for review."""
    template_name = 'social/moderation/queue.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['flagged_posts'] = Post.objects.filter(is_flagged=True).order_by('-created_at')[:50]
        context['flagged_comments'] = Comment.objects.filter(is_flagged=True).order_by('-created_at')[:50]
        context.update(get_moderation_context(self.request))
        return context


class ModerationUsersView(ModeratorRequiredMixin, TemplateView):
    """User management overview for moderators (suspensions, bans)."""
    template_name = 'social/moderation/users.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['suspended_profiles'] = UserProfile.objects.filter(is_suspended=True).order_by('-updated_at')[:50]
        context.update(get_moderation_context(self.request))
        return context
