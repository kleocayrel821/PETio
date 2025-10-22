from django.urls import path
from . import views

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
    path('post/<int:post_id>/comment/', views.comment_create, name='comment_create'),
    
    # AJAX endpoints
    path('post/<int:post_id>/like/', views.toggle_like, name='toggle_like'),
    path('user/<int:user_id>/follow/', views.toggle_follow, name='toggle_follow'),
    
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
]