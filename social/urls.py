from django.urls import path
from . import views

app_name = 'social'

urlpatterns = [
    # Top-level
    path('', views.feed, name='feed'),
    path('friends/', views.friends, name='friends'),
    # messages removed (direct messaging deprecated)
    path('notifications/', views.notifications, name='notifications'),
    path('profile/', views.profile, name='profile'),

    # Forum
    path('forum/', views.forum_categories, name='forum_categories'),
    path('forum/new/', views.new_thread, name='new_thread'),
    path('forum/c/<slug:category_slug>/', views.forum_threads, name='forum_threads'),
    path('forum/t/<int:thread_id>/', views.thread_detail, name='thread_detail'),
]