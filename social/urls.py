from django.urls import path
from . import views
from .moderation_views import (
    ModerationDashboardView,
    ModerationReportsView,
    ReportDetailView,
)

app_name = 'social'

urlpatterns = [
    # Main pages
    path('', views.feed, name='feed'),
    path('feed/', views.feed, name='feed_page'),
    path('home/', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Post management
    path('create/', views.create_post, name='create_post'),
    path('post/<int:pk>/', views.post_detail, name='post_detail'),
    path('post/<int:pk>/edit/', views.edit_post, name='edit_post'),
    path('post/<int:pk>/delete/', views.delete_post, name='delete_post'),
    path('post/<int:pk>/report/', views.report_post, name='report_post'),
    path('post/<int:post_id>/comment/', views.comment_create, name='comment_create'),
    
    # AJAX endpoints
    path('post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('user/<int:user_id>/follow/', views.toggle_follow, name='toggle_follow'),
    path('user/<int:user_id>/followers/', views.user_followers, name='user_followers'),
    path('user/<int:user_id>/following/', views.user_following, name='user_following'),
    path('user/<int:user_id>/likes/', views.user_likes, name='user_likes'),
    
    # User profiles (ensure 'edit' route precedes '<username>' route)
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/', views.profile, name='my_profile'),
    path('profile/<str:username>/', views.profile, name='profile'),
    
    # Notifications
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/count/', views.notification_count, name='notification_count'),
    path('notifications/<int:pk>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/<int:pk>/delete/', views.delete_notification, name='delete_notification'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
    path('notifications/clear-all/', views.clear_all_notifications, name='clear_all_notifications'),

    # Moderation endpoints
    path('moderation/', ModerationDashboardView.as_view(), name='moderation_dashboard'),
    path('moderation/reports/', ModerationReportsView.as_view(), name='moderation_reports'),
    # Moderation - Content Actions
    path('moderation/post/<int:post_id>/approve/', views.approve_post, name='approve_post'),
    path('moderation/post/<int:post_id>/hide/', views.hide_post, name='hide_post'),
    path('moderation/post/<int:post_id>/delete/', views.moderate_delete_post, name='moderate_delete_post'),
    path('moderation/comment/<int:comment_id>/approve/', views.approve_comment, name='approve_comment'),
    path('moderation/comment/<int:comment_id>/hide/', views.hide_comment, name='hide_comment'),
    path('moderation/comment/<int:comment_id>/delete/', views.moderate_delete_comment, name='moderate_delete_comment'),

    # Moderation - User Actions
    path('moderation/user/<int:user_id>/warn/', views.warn_user, name='warn_user'),
    path('moderation/user/<int:user_id>/suspend/', views.suspend_user, name='suspend_user'),
    path('moderation/user/<int:user_id>/ban/', views.ban_user, name='ban_user'),
    path('moderation/user/<int:user_id>/unsuspend/', views.unsuspend_user, name='unsuspend_user'),

    # Moderation - Report Actions
    path('moderation/report/<int:pk>/resolve/', views.resolve_report, name='resolve_report'),
    path('moderation/report/<int:pk>/dismiss/', views.dismiss_report, name='dismiss_report'),

    # Moderation - Views (FBVs)
    path('moderation/queue/', views.moderation_queue, name='moderation_queue'),
    path('moderation/users/', views.moderation_users, name='moderation_users'),
    path('moderation/logs/', views.moderation_logs, name='moderation_logs'),
    path('report/<int:pk>/', ReportDetailView.as_view(), name='report_detail'),
]