from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q, Count
from datetime import timedelta
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Post, Category, Comment, Like, UserProfile, Follow, Notification
import json
from .forms import PostForm, CommentForm, ProfileForm

# Use the project's configured User model (supports custom accounts.User)
User = get_user_model()


def home(request):
    """Home/Landing page for IOsocial"""
    # Calculate community stats for the home page
    total_users = User.objects.count()
    total_posts = Post.objects.count()
    total_interactions = Like.objects.count() + Comment.objects.count()
    
    context = {
        'total_users': total_users,
        'total_posts': total_posts,
        'total_interactions': total_interactions,
    }
    
    return render(request, 'social/home.html', context)


def feed(request):
    """Community feed showing all posts"""
    # Get filter parameters
    category_filter = request.GET.get('category')
    search_query = request.GET.get('search')
    sort_by = request.GET.get('sort', 'recent')
    
    # Base queryset
    posts = Post.objects.select_related('author', 'category').prefetch_related('likes', 'comments')
    
    # Apply filters
    if category_filter:
        posts = posts.filter(category__name__iexact=category_filter)
    
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) | 
            Q(content__icontains=search_query) |
            Q(author__username__icontains=search_query)
        )
    
    # Apply sorting
    if sort_by == 'popular':
        # Avoid property name conflict by using a different annotation name
        posts = posts.annotate(likes_count=Count('likes')).order_by('-likes_count', '-created_at')
    elif sort_by == 'recent':
        posts = posts.order_by('-is_pinned', '-created_at')
    
    # Pagination
    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Get categories for filter and popular categories for sidebar
    categories = Category.objects.all()
    popular_categories = Category.objects.annotate(posts_count=Count('post', distinct=True)).order_by('-posts_count', 'name')[:5]
    
    # Community stats for sidebar
    week_ago = timezone.now() - timedelta(days=7)
    community_stats = {
        'total_posts': Post.objects.count(),
        'active_members': User.objects.annotate(post_count=Count('social_posts')).filter(post_count__gt=0).count(),
        'this_week_posts': Post.objects.filter(created_at__gte=week_ago).count(),
    }
    
    context = {
        'page_obj': page_obj,
        'categories': categories,
        'popular_categories': popular_categories,
        'community_stats': community_stats,
        'current_category': category_filter,
        'search_query': search_query,
        'sort_by': sort_by,
    }
    
    return render(request, 'social/feed.html', context)


@login_required
def create_post(request):
    """Create a new post"""
    if request.method == 'POST':
        save_draft = request.POST.get('save_draft')
        # Handle draft saving (AJAX request)
        if save_draft:
            return JsonResponse({'success': True, 'message': 'Draft saved successfully!'})
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            messages.success(request, 'Post created successfully!')
            return redirect('social:post_detail', pk=post.pk)
        else:
            # Re-render template with errors but maintain existing mockup UI
            categories = Category.objects.all()
            return render(request, 'social/create_post.html', {
                'categories': categories,
                'form_errors': form.errors,
            })
    categories = Category.objects.all()
    return render(request, 'social/create_post.html', {'categories': categories})


def post_detail(request, pk):
    """Detailed view of a single post"""
    post = get_object_or_404(Post, pk=pk)
    comments = post.comments.filter(parent=None).select_related('author').prefetch_related('replies')
    
    # Handle comment submission via normal POST
    if request.method == 'POST' and request.user.is_authenticated:
        form = CommentForm(request.POST)
        parent_id = request.POST.get('parent_id')
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            # Handle parent reply
            if parent_id:
                try:
                    parent_comment = Comment.objects.get(id=parent_id, post=post)
                    comment.parent = parent_comment
                except Comment.DoesNotExist:
                    pass
            comment.save()
            # Create notification for post author
            if post.author != request.user:
                Notification.objects.create(
                    recipient=post.author,
                    sender=request.user,
                    notification_type='comment',
                    post=post,
                    comment=comment,
                    message=f'{request.user.username} commented on your post'
                )
            messages.success(request, 'Comment added successfully!')
            return redirect('social:post_detail', pk=post.pk)
    
    context = {
        'post': post,
        'comments': comments,
        'user_has_liked': post.likes.filter(id=request.user.id).exists() if request.user.is_authenticated else False,
        'comment_form': CommentForm(),
    }
    
    return render(request, 'social/post_detail.html', context)


@login_required
@require_POST
def comment_create(request, post_id):
    """Create a comment via AJAX (CSRF-safe)"""
    post = get_object_or_404(Post, id=post_id)
    form = CommentForm(request.POST)
    parent_id = request.POST.get('parent_id')
    if form.is_valid():
        comment = form.save(commit=False)
        comment.post = post
        comment.author = request.user
        if parent_id:
            try:
                parent_comment = Comment.objects.get(id=parent_id, post=post)
                comment.parent = parent_comment
            except Comment.DoesNotExist:
                pass
        comment.save()
        # Create notification for post author
        if post.author != request.user:
            Notification.objects.create(
                recipient=post.author,
                sender=request.user,
                notification_type='comment',
                post=post,
                comment=comment,
                message=f'{request.user.username} commented on your post'
            )
        return JsonResponse({
            'ok': True,
            'comment': {
                'id': comment.id,
                'author': request.user.username,
                'content': comment.content,
                'created_at': timezone.localtime(comment.created_at).strftime('%Y-%m-%d %H:%M'),
                'is_reply': bool(comment.parent_id),
            },
            'comment_count': post.comment_count,
        })
    return JsonResponse({'ok': False, 'errors': form.errors}, status=400)


@login_required
def dashboard(request):
    """User dashboard showing posts, stats, and recent activity"""
    user = request.user
    
    # Ensure user profile exists
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Core querysets with select_related for better performance
    user_posts_qs = Post.objects.filter(author=user).select_related('category')
    recent_posts = user_posts_qs.order_by('-created_at')[:5]
    
    # Popular posts with proper annotation
    popular_posts = user_posts_qs.annotate(
        likes_count=Count('likes')
    ).order_by('-likes_count', '-created_at')[:5]
    
    # Recent notifications with related data
    recent_notifications = Notification.objects.filter(
        recipient=user
    ).select_related('sender', 'post').order_by('-created_at')[:5]
    
    # Calculate user statistics
    total_posts = user_posts_qs.count()
    total_likes = Like.objects.filter(post__author=user).count()
    total_comments = Comment.objects.filter(post__author=user).count()
    
    # Get follower/following counts directly from the database
    followers_count = Follow.objects.filter(following=user).count()
    following_count = Follow.objects.filter(follower=user).count()
    
    user_stats = {
        'total_posts': total_posts,
        'total_likes': total_likes,
        'total_comments': total_comments,
        'followers_count': followers_count,
        'following_count': following_count,
    }
    
    # Weekly activity stats
    week_ago = timezone.now() - timedelta(days=7)
    weekly_stats = {
        'posts': user_posts_qs.filter(created_at__gte=week_ago).count(),
        'likes': Like.objects.filter(post__author=user, created_at__gte=week_ago).count(),
        'comments': Comment.objects.filter(post__author=user, created_at__gte=week_ago).count(),
        'followers': Follow.objects.filter(following=user, created_at__gte=week_ago).count(),
    }
    
    context = {
        'profile': profile,
        'user_stats': user_stats,
        'recent_posts': recent_posts,
        'popular_posts': popular_posts,
        'recent_notifications': recent_notifications,
        'weekly_stats': weekly_stats,
    }
    return render(request, 'social/dashboard.html', context)


@login_required
@require_POST
def toggle_like(request, post_id):
    """Toggle like status for a post (AJAX)"""
    post = get_object_or_404(Post, id=post_id)
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    
    if not created:
        like.delete()
        liked = False
    else:
        liked = True
        # Create notification for post author
        if post.author != request.user:
            Notification.objects.create(
                recipient=post.author,
                sender=request.user,
                notification_type='like',
                post=post,
                message=f'{request.user.username} liked your post'
            )
    
    return JsonResponse({
        'liked': liked,
        'like_count': post.like_count
    })


@login_required
def profile(request, username=None):
    """User profile view"""
    if username:
        user = get_object_or_404(User, username=username)
    else:
        user = request.user
    
    profile, created = UserProfile.objects.get_or_create(user=user)
    user_posts = Post.objects.filter(author=user).order_by('-created_at')[:10]
    
    # Check if current user follows this profile
    is_following = False
    if request.user.is_authenticated and request.user != user:
        is_following = Follow.objects.filter(follower=request.user, following=user).exists()
    
    context = {
        'profile_user': user,
        'profile': profile,
        'user_posts': user_posts,
        'is_following': is_following,
        'is_own_profile': request.user == user,
    }
    
    return render(request, 'social/profile.html', context)


@login_required
@require_POST
def toggle_follow(request, user_id):
    """Toggle follow status for a user (AJAX)"""
    user_to_follow = get_object_or_404(User, id=user_id)
    
    if user_to_follow == request.user:
        return JsonResponse({'error': 'Cannot follow yourself'}, status=400)
    
    follow, created = Follow.objects.get_or_create(
        follower=request.user,
        following=user_to_follow
    )
    
    if not created:
        follow.delete()
        following = False
    else:
        following = True
        # Create notification
        Notification.objects.create(
            recipient=user_to_follow,
            sender=request.user,
            notification_type='follow',
            message=f'{request.user.username} started following you'
        )
    
    return JsonResponse({
        'following': following,
        'follower_count': user_to_follow.social_profile.follower_count
    })


@login_required
def notifications(request):
    """User notifications"""
    user_notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    
    # Mark notifications as read
    user_notifications.filter(is_read=False).update(is_read=True)
    
    # Pagination
    paginator = Paginator(user_notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'social/notifications.html', {'page_obj': page_obj})


@login_required
def edit_post(request, pk):
    """Edit an existing post"""
    post = get_object_or_404(Post, pk=pk, author=request.user)
    
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, 'Post updated successfully!')
            return redirect('social:post_detail', pk=post.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    categories = Category.objects.all()
    context = {
        'post': post,
        'categories': categories,
    }
    return render(request, 'social/edit_post.html', context)


@login_required
@require_POST
def delete_post(request, pk):
    """Delete a post"""
    post = get_object_or_404(Post, pk=pk, author=request.user)
    post.delete()
    messages.success(request, 'Post deleted successfully!')
    return redirect('social:dashboard')


@login_required
def notification_count(request):
    """Get unread notification count (AJAX)"""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'count': count})


@login_required
@require_POST
def mark_notification_read(request, pk):
    """Mark a single notification as read"""
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
        messages.success(request, 'Notification marked as read.')
    return redirect('social:notifications')


@login_required
@require_POST
def delete_notification(request, pk):
    """Delete a single notification"""
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.delete()
    messages.success(request, 'Notification deleted.')
    return redirect('social:notifications')


@login_required
@require_POST
def mark_all_notifications_read(request):
    """Mark all of the user's notifications as read"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, 'All notifications marked as read.')
    return redirect('social:notifications')


@login_required
@require_POST
def clear_all_notifications(request):
    """Delete all of the user's notifications"""
    Notification.objects.filter(recipient=request.user).delete()
    messages.success(request, 'All notifications cleared.')
    return redirect('social:notifications')


@login_required
def edit_profile(request):
    """Edit user profile"""
    profile, created = UserProfile.objects.get_or_create(user=request.user)
    
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profile updated successfully!')
            return redirect('social:profile', username=request.user.username)
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = ProfileForm(instance=profile)
    
    return render(request, 'social/edit_profile.html', {'form': form, 'profile': profile})