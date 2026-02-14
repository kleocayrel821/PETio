from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib import messages
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db import transaction, models
from django.db.models import Q, Count
from datetime import timedelta, datetime
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import Post, Category, Comment, Like, UserProfile, Follow, Notification, SocialReport, ModerationAction, UserSuspension, PostImage, PostVideo
from .mixins import ModeratorRequiredMixin  # for parity with permissions logic
from .permissions import is_moderator
from .decorators import moderator_required, admin_required
import json
from .forms import PostForm, CommentForm, ProfileForm
from django.urls import reverse
from .forms import PostForm, CommentForm, ProfileForm, SocialReportForm
import logging

logger = logging.getLogger(__name__)

# Use the project's configured User model (supports custom accounts.User)
User = get_user_model()


@login_required
def home(request):
    """Home/Landing page for IOsocial"""
    # Calculate community stats for the home page
    total_users = User.objects.exclude(username__startswith='smoke_').count()
    total_posts = Post.objects.exclude(author__username__startswith='smoke_').count()
    total_interactions = (
        Like.objects.exclude(post__author__username__startswith='smoke_').count()
        + Comment.objects.exclude(post__author__username__startswith='smoke_').count()
    )
    
    context = {
        'total_users': total_users,
        'total_posts': total_posts,
        'total_interactions': total_interactions,
    }
    
    return render(request, 'social/home.html', context)


@login_required
def feed(request):
    """Community feed showing all posts"""
    search_query = request.GET.get('search')
    sort_by = request.GET.get('sort', 'recent')
    
    posts = (
        Post.objects
        .select_related('author')
        .prefetch_related('likes', 'comments', 'images', 'videos')
        .exclude(author__username__startswith='smoke_')
    )
    
    if search_query:
        posts = posts.filter(
            Q(title__icontains=search_query) | 
            Q(content__icontains=search_query) |
            Q(author__username__icontains=search_query)
        )

    user_results = []
    if search_query:
        user_results = (
            User.objects
            .select_related('social_profile')
            .filter(
                Q(username__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(social_profile__bio__icontains=search_query) |
                Q(social_profile__location__icontains=search_query)
            )
            .exclude(username__startswith='smoke_')
            .annotate(
                followers_count=Count('social_followers_set'),
                post_count=Count('social_posts')
            )
            .order_by('-followers_count', '-post_count', '-date_joined')[:20]
        )
    
    if sort_by == 'popular':
        posts = posts.annotate(likes_count=Count('likes')).order_by('-likes_count', '-created_at')
    else:
        posts = posts.order_by('-is_pinned', '-created_at')
    
    paginator = Paginator(posts, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    post_ids = [p.id for p in page_obj.object_list]
    root_qs = (
        Comment.objects.filter(
            post_id__in=post_ids,
            parent__isnull=True,
            hidden_at__isnull=True,
        )
        .exclude(author__username__startswith='smoke_')
        .select_related('author')
        .order_by('created_at')
    )
    root_map = {}
    for c in root_qs:
        root_map.setdefault(c.post_id, []).append(c)
    root_counts = (
        Comment.objects.filter(
            post_id__in=post_ids,
            parent__isnull=True,
            hidden_at__isnull=True,
        )
        .exclude(author__username__startswith='smoke_')
        .values('post_id')
        .annotate(cnt=Count('id'))
    )
    count_map = {rc['post_id']: rc['cnt'] for rc in root_counts}
    for p in page_obj.object_list:
        lst = root_map.get(p.id, [])
        p.root_comments = lst[:2]
        p.root_comment_total = count_map.get(p.id, 0)
    
    week_ago = timezone.now() - timedelta(days=7)
    community_stats = {
        'total_posts': Post.objects.exclude(author__username__startswith='smoke_').count(),
        'active_members': User.objects.annotate(post_count=Count('social_posts')).filter(post_count__gt=0).exclude(username__startswith='smoke_').count(),
        'this_week_posts': Post.objects.filter(created_at__gte=week_ago).exclude(author__username__startswith='smoke_').count(),
    }
    friend_suggestions = []
    if request.user.is_authenticated:
        following_ids = Follow.objects.filter(follower=request.user).values_list('following_id', flat=True)
        friend_suggestions = (
            User.objects
            .exclude(id__in=list(following_ids))
            .exclude(id=request.user.id)
            .exclude(username__startswith='smoke_')
            .filter(is_staff=False, is_superuser=False)
            .annotate(
                followers_count=Count('social_followers_set'),
                post_count=Count('social_posts')
            )
            .order_by('-followers_count', '-post_count', '-date_joined')[:6]
        )
    
    context = {
        'page_obj': page_obj,
        'community_stats': community_stats,
        'search_query': search_query,
        'sort_by': sort_by,
        'search_type': 'all',
        'user_results': user_results,
        'friend_suggestions': friend_suggestions,
    }
    context.update(get_moderation_context(request))
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
            from .models import PostImage, PostVideo
            files = request.FILES.getlist('images') or request.FILES.getlist('media')
            for f in files:
                ct = getattr(f, 'content_type', '') or ''
                name = getattr(f, 'name', '') or ''
                ext = name.lower().rsplit('.', 1)[-1] if '.' in name else ''
                if ct.startswith('image/') or ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                    PostImage.objects.create(post=post, image=f)
                elif ct.startswith('video/') or ext in ('mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv'):
                    PostVideo.objects.create(post=post, file=f)
            messages.success(request, 'Post created successfully!')
            return redirect('social:post_detail', pk=post.pk)
        else:
            return render(request, 'social/create_post.html', {
                'form_errors': form.errors,
            })
    return render(request, 'social/create_post.html')


@login_required
def post_detail(request, pk):
    """Detailed view of a single post"""
    post = get_object_or_404(Post.objects.prefetch_related('images', 'videos', 'likes', 'comments'), pk=pk)
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
    user_posts = Post.objects.filter(author=user).prefetch_related('images', 'videos', 'likes', 'comments').order_by('-created_at')[:10]
    
    # Check if current user follows this profile
    is_following = False
    if request.user.is_authenticated and request.user != user:
        is_following = Follow.objects.filter(follower=request.user, following=user).exists()
    
    # Likes data: viewer's liked posts for heart state, and profile user's total likes
    viewer_liked_post_ids = []
    if request.user.is_authenticated:
        viewer_liked_post_ids = list(Like.objects.filter(user=request.user).values_list('post_id', flat=True))
    profile_likes_count = Like.objects.filter(user=user).count()
    
    context = {
        'profile_user': user,
        'profile': profile,
        'user_posts': user_posts,
        'is_following': is_following,
        'is_own_profile': request.user == user,
        'viewer_liked_post_ids': viewer_liked_post_ids,
        'profile_likes_count': profile_likes_count,
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
    unread_count = user_notifications.filter(is_read=False).count()
    user_notifications.filter(is_read=False).update(is_read=True)
    
    # Pagination
    paginator = Paginator(user_notifications, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'social/notifications.html', {'page_obj': page_obj, 'unread_count': unread_count})


@login_required
def edit_post(request, pk):
    """Edit an existing post"""
    post = get_object_or_404(Post, pk=pk, author=request.user)
    
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            form.save()
            # Handle featured image replace/clear (not part of PostForm)
            try:
                if request.POST.get('image-clear'):
                    post.image = None
                    post.save(update_fields=['image'])
                elif 'image' in request.FILES:
                    post.image = request.FILES['image']
                    post.save(update_fields=['image'])
            except Exception as e:
                logger.error('Failed to update featured image for post_id=%s error=%s', post.pk, e)
            # Remove selected existing additional images
            remove_ids = request.POST.getlist('remove_image_ids')
            if remove_ids:
                try:
                    PostImage.objects.filter(post=post, id__in=remove_ids).delete()
                except Exception as e:
                    logger.error('Failed to remove images for post_id=%s ids=%s error=%s', post.pk, remove_ids, e)
            # Add newly selected additional media (images/videos)
            files = request.FILES.getlist('images')
            for f in files:
                ct = getattr(f, 'content_type', '') or ''
                name = getattr(f, 'name', '') or ''
                ext = name.lower().rsplit('.', 1)[-1] if '.' in name else ''
                if ct.startswith('image/') or ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
                    PostImage.objects.create(post=post, image=f)
                elif ct.startswith('video/') or ext in ('mp4', 'webm', 'mov', 'm4v', 'avi', 'mkv'):
                    from .models import PostVideo
                    PostVideo.objects.create(post=post, file=f)
            # Remove selected existing videos
            remove_vid_ids = request.POST.getlist('remove_video_ids')
            if remove_vid_ids:
                try:
                    from .models import PostVideo
                    PostVideo.objects.filter(post=post, id__in=remove_vid_ids).delete()
                except Exception as e:
                    logger.error('Failed to remove videos for post_id=%s ids=%s error=%s', post.pk, remove_vid_ids, e)
            messages.success(request, 'Post updated successfully!')
            return redirect('social:post_detail', pk=post.pk)
        else:
            messages.error(request, 'Please correct the errors below.')
    context = {
        'post': post,
    }
    return render(request, 'social/edit_post.html', context)


@login_required
@require_POST
def delete_post(request, pk):
    """Delete a post"""
    post = get_object_or_404(Post, pk=pk, author=request.user)
    post.delete()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'post_id': pk})
    messages.success(request, 'Post deleted successfully!')
    return redirect('social:dashboard')


@login_required
def report_post(request, pk):
    """
    Allow a logged-in user to report a disturbing post.

    GET: Render a small form to select a report type and provide an optional
    description.
    POST: Create a `SocialReport` for the post, flag the post for moderation,
    and redirect back to the post detail with a success message.
    """
    post = get_object_or_404(Post, pk=pk)

    # Authors should not report their own post (use edit/delete instead)
    if request.user == post.author:
        messages.info(request, 'You can edit or delete your own post instead of reporting it.')
        logger.warning('Self-report attempted: user=%s post_id=%s', request.user.username, post.pk)
        return redirect('social:post_detail', pk=pk)

    if request.method == 'POST':
        form = SocialReportForm(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.reporter = request.user
            report.reported_post = post
            report.reported_user = post.author
            report.save()
            logger.info('SocialReport created: id=%s type=%s reporter=%s post_id=%s', report.pk, report.report_type, request.user.username, post.pk)

            # Flag the post so it appears in the moderation queue
            if not post.is_flagged:
                post.is_flagged = True
                post.save(update_fields=['is_flagged'])

            messages.success(request, 'Thanks for reporting. Our moderators will review it soon.')
            return redirect('social:post_detail', pk=pk)
        else:
            messages.error(request, 'Please fix the errors below and resubmit.')
            logger.error('Report form invalid for post_id=%s errors=%s', post.pk, form.errors)
    else:
        form = SocialReportForm()

    context = {
        'post': post,
        'form': form,
    }
    return render(request, 'social/report_post.html', context)


@login_required
def notification_count(request):
    """Get unread notification count (AJAX)"""
    count = Notification.objects.filter(recipient=request.user, is_read=False).count()
    return JsonResponse({'count': count})


@login_required
def user_followers(request, user_id):
    """Return followers of a user as JSON"""
    user = get_object_or_404(User, id=user_id)
    qs = Follow.objects.filter(following=user).select_related('follower')
    results = []
    for rel in qs[:100]:
        u = rel.follower
        avatar_url = getattr(getattr(u, 'social_profile', None), 'avatar', None)
        avatar_url = avatar_url.url if avatar_url else None
        results.append({
            'id': u.id,
            'username': u.username,
            'avatar_url': avatar_url,
            'profile_url': reverse('social:profile', kwargs={'username': u.username}),
            'extra': f"Following since {rel.created_at.strftime('%b %d, %Y')}"
        })
    return JsonResponse({'count': qs.count(), 'results': results})


@login_required
def user_following(request, user_id):
    """Return users that the given user is following as JSON"""
    user = get_object_or_404(User, id=user_id)
    qs = Follow.objects.filter(follower=user).select_related('following')
    results = []
    for rel in qs[:100]:
        u = rel.following
        avatar_url = getattr(getattr(u, 'social_profile', None), 'avatar', None)
        avatar_url = avatar_url.url if avatar_url else None
        results.append({
            'id': u.id,
            'username': u.username,
            'avatar_url': avatar_url,
            'profile_url': reverse('social:profile', kwargs={'username': u.username}),
            'extra': f"Followed since {rel.created_at.strftime('%b %d, %Y')}"
        })
    return JsonResponse({'count': qs.count(), 'results': results})


@login_required
def user_likes(request, user_id):
    """Return posts liked by the user as JSON"""
    user = get_object_or_404(User, id=user_id)
    qs = Like.objects.filter(user=user).select_related('post')
    results = []
    for like in qs[:100]:
        p = like.post
        image_url = p.image.url if p.image else None
        excerpt = (p.content[:140] + '...') if p.content and len(p.content) > 140 else p.content
        results.append({
            'id': p.id,
            'title': p.title,
            'excerpt': excerpt,
            'created_at': p.created_at.strftime('%b %d, %Y'),
            'image_url': image_url,
            'url': reverse('social:post_detail', kwargs={'pk': p.id})
        })
    return JsonResponse({'count': qs.count(), 'results': results})


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


def get_moderation_context(request):
    """
    Helper function to get moderation-related context data.
    Used to populate sidebar badges and notification counts.

    Returns empty dict for non-authenticated users or non-moderators.
    """
    # Bail out early if not authenticated
    if not request.user.is_authenticated:
        return {}

    # Only active for moderators/staff
    if not is_moderator(request.user):
        return {}

    context = {
        'is_moderator': True,
        'pending_reports_count': SocialReport.objects.filter(status='pending').count(),
        'reviewing_reports_count': SocialReport.objects.filter(status='reviewing').count(),
        'flagged_posts_count': Post.objects.filter(is_flagged=True).count(),
        'flagged_comments_count': Comment.objects.filter(is_flagged=True).count(),
    }

    return context


# =============================
# Phase 3: Moderation Actions
# =============================

@moderator_required
@require_POST
def approve_post(request, post_id):
    """
    Approve a flagged post (make it visible again).
    AJAX endpoint.
    """
    post = get_object_or_404(Post, pk=post_id)

    # Update post visibility and flags to restore
    post.is_flagged = False
    post.hidden_at = None
    post.save(update_fields=['is_flagged', 'hidden_at'])

    # Log the action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='restore_post',
        target_post=post,
        target_user=post.author,
        reason=request.POST.get('reason', 'Post approved by moderator'),
    )

    messages.success(request, f'Post "{post.title}" has been approved.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Post approved successfully'
        })

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@moderator_required
@require_POST
def hide_post(request, post_id):
    """
    Hide a post without deleting it (soft delete).
    AJAX endpoint.
    """
    post = get_object_or_404(Post, pk=post_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'error': 'Reason is required'
            }, status=400)
        messages.error(request, 'Reason is required to hide content.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Hide the post by setting hidden_at
    post.hidden_at = timezone.now()
    post.save(update_fields=['hidden_at'])

    # Log the action
    action = ModerationAction.objects.create(
        moderator=request.user,
        action_type='hide_post',
        target_post=post,
        target_user=post.author,
        reason=reason,
    )

    # Notify the post author
    Notification.objects.create(
        recipient=post.author,
        sender=request.user,
        notification_type='mention',  # Using existing type
        post=post,
        message=f'Your post has been hidden by moderation: {reason}'
    )

    messages.success(request, f'Post "{post.title}" has been hidden.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Post hidden successfully',
            'action_id': action.id
        })

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@moderator_required
@require_POST
def moderate_delete_post(request, post_id):
    """
    Permanently delete a post (hard delete).
    Only for severe violations.
    """
    post = get_object_or_404(Post, pk=post_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        messages.error(request, 'Reason is required to delete content.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Store post info before deletion
    post_title = post.title
    post_author = post.author

    # Log the action before deleting
    action = ModerationAction.objects.create(
        moderator=request.user,
        action_type='delete_post',
        target_user=post_author,
        target_post=post,
        reason=reason,
    )

    # Notify the author
    Notification.objects.create(
        recipient=post_author,
        sender=request.user,
        notification_type='mention',
        message=f'Your post "{post_title}" was removed for violating community guidelines: {reason}'
    )

    # Delete the post
    post.delete()

    messages.success(request, f'Post "{post_title}" has been permanently deleted.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'message': 'Post deleted successfully',
            'action_id': action.id
        })

    return redirect('social:moderation_dashboard')


@moderator_required
@require_POST
def approve_comment(request, comment_id):
    """
    Approve a flagged comment.
    AJAX endpoint.
    """
    comment = get_object_or_404(Comment, pk=comment_id)

    comment.is_flagged = False
    comment.hidden_at = None
    comment.save(update_fields=['is_flagged', 'hidden_at'])

    ModerationAction.objects.create(
        moderator=request.user,
        action_type='restore_comment',
        target_comment=comment,
        target_user=comment.author,
        reason=request.POST.get('reason', 'Comment approved by moderator'),
    )

    messages.success(request, 'Comment has been approved.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': 'Comment approved'})

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@moderator_required
@require_POST
def hide_comment(request, comment_id):
    """
    Hide a comment without deleting it.
    AJAX endpoint.
    """
    comment = get_object_or_404(Comment, pk=comment_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Reason required'}, status=400)
        messages.error(request, 'Reason is required.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    comment.hidden_at = timezone.now()
    comment.save(update_fields=['hidden_at'])

    action = ModerationAction.objects.create(
        moderator=request.user,
        action_type='hide_comment',
        target_comment=comment,
        target_user=comment.author,
        reason=reason,
    )

    Notification.objects.create(
        recipient=comment.author,
        sender=request.user,
        notification_type='mention',
        comment=comment,
        message=f'Your comment was hidden by moderation: {reason}'
    )

    messages.success(request, 'Comment has been hidden.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'action_id': action.id})

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@moderator_required
@require_POST
def moderate_delete_comment(request, comment_id):
    """
    Permanently delete a comment.
    """
    comment = get_object_or_404(Comment, pk=comment_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        messages.error(request, 'Reason is required to delete content.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    comment_author = comment.author
    comment_content = (comment.content or '')[:50]

    action = ModerationAction.objects.create(
        moderator=request.user,
        action_type='delete_comment',
        target_user=comment_author,
        target_comment=comment,
        reason=reason,
    )

    Notification.objects.create(
        recipient=comment_author,
        sender=request.user,
        notification_type='mention',
        message=f'Your comment was removed for violating guidelines: {reason}'
    )

    comment.delete()

    messages.success(request, 'Comment has been deleted.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'action_id': action.id})

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@moderator_required
@require_POST
def warn_user(request, user_id):
    """
    Issue a warning to a user.
    Increments warning count (derived from actions) and may auto-suspend.
    """
    target_user = get_object_or_404(User, pk=user_id)
    reason = request.POST.get('reason', '').strip()
    warning_message = request.POST.get('message', '').strip()

    if not reason:
        messages.error(request, 'Reason is required to issue a warning.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Ensure profile exists
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    # Log the warning action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='warn',
        target_user=target_user,
        reason=reason,
    )

    # Compute current warning count from actions
    warnings_count = ModerationAction.objects.filter(
        target_user=target_user, action_type='warn'
    ).count()

    # Notify the user
    message = warning_message or f'You have received a warning from moderation: {reason}'
    Notification.objects.create(
        recipient=target_user,
        sender=request.user,
        notification_type='mention',
        message=message
    )

    # Auto-suspend after threshold (e.g., 3 warnings)
    if warnings_count >= 3 and not profile.is_suspended:
        suspension_end = timezone.now() + timedelta(days=7)
        profile.is_suspended = True
        profile.suspended_until = suspension_end
        profile.suspension_reason = 'Automatic suspension after 3 warnings'
        profile.save(update_fields=['is_suspended', 'suspended_until', 'suspension_reason'])

        # Create suspension record
        UserSuspension.objects.create(
            user=target_user,
            reason='Automatic suspension after 3 warnings',
            end_at=suspension_end,
            is_active=True,
            created_by=request.user,
        )

        messages.warning(
            request,
            'Warning issued. User has been automatically suspended for 7 days (3+ warnings).'
        )
    else:
        messages.success(
            request,
            f'Warning issued to {target_user.username}. Total warnings: {warnings_count}'
        )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'warnings_count': warnings_count,
        })

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@admin_required
@require_POST
@transaction.atomic
def suspend_user(request, user_id):
    """
    Suspend a user for a specified duration.
    Only admins can suspend users.
    """
    target_user = get_object_or_404(User, pk=user_id)
    reason = request.POST.get('reason', '').strip()
    duration_days = request.POST.get('duration_days', '').strip()

    if not reason:
        messages.error(request, 'Reason is required to suspend a user.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Parse duration
    try:
        days = int(duration_days) if duration_days else 7
        if days <= 0:
            raise ValueError()
    except ValueError:
        messages.error(request, 'Invalid suspension duration.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Calculate end date
    suspension_end = timezone.now() + timedelta(days=days)

    # Get or create profile
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.is_suspended = True
    profile.suspended_until = suspension_end
    profile.suspension_reason = reason
    profile.save(update_fields=['is_suspended', 'suspended_until', 'suspension_reason'])

    # Create suspension record
    suspension = UserSuspension.objects.create(
        user=target_user,
        reason=reason,
        end_at=suspension_end,
        is_active=True,
        created_by=request.user,
    )

    # Log the action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='suspend',
        target_user=target_user,
        reason=f'Duration: {days} days\n{reason}',
    )

    # Notify the user
    Notification.objects.create(
        recipient=target_user,
        sender=request.user,
        notification_type='mention',
        message=f'Your account has been suspended for {days} days. Reason: {reason}'
    )

    messages.success(
        request,
        f'User {target_user.username} has been suspended for {days} days.'
    )

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'suspension_id': suspension.id,
            'end_date': suspension_end.isoformat(),
        })

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@admin_required
@require_POST
@transaction.atomic
def ban_user(request, user_id):
    """
    Permanently ban a user.
    Only admins can ban users.
    """
    target_user = get_object_or_404(User, pk=user_id)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        messages.error(request, 'Reason is required to ban a user.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Get or create profile
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    profile.is_suspended = True
    profile.suspended_until = None  # Permanent
    profile.suspension_reason = reason
    profile.save(update_fields=['is_suspended', 'suspended_until', 'suspension_reason'])

    # Create permanent suspension record
    suspension = UserSuspension.objects.create(
        user=target_user,
        reason=reason,
        end_at=None,  # Permanent ban
        is_active=True,
        created_by=request.user,
    )

    # Log the action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='ban',
        target_user=target_user,
        reason=f'Permanent ban\n{reason}',
    )

    # Notify the user
    Notification.objects.create(
        recipient=target_user,
        sender=request.user,
        notification_type='mention',
        message=f'Your account has been permanently banned. Reason: {reason}'
    )

    messages.success(request, f'User {target_user.username} has been permanently banned.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'suspension_id': suspension.id,
        })

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@admin_required
@require_POST
@transaction.atomic
def unsuspend_user(request, user_id):
    """
    Lift a user's suspension early.
    Only admins can unsuspend users.
    """
    target_user = get_object_or_404(User, pk=user_id)
    reason = request.POST.get('reason', 'Suspension lifted by administrator').strip()

    # Get profile
    profile = get_object_or_404(UserProfile, user=target_user)

    if not profile.is_suspended:
        messages.warning(request, 'User is not currently suspended.')
        return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))

    # Update profile
    profile.is_suspended = False
    profile.suspended_until = None
    profile.suspension_reason = ''
    profile.save(update_fields=['is_suspended', 'suspended_until', 'suspension_reason'])

    # Deactivate active suspensions
    now = timezone.now()
    UserSuspension.objects.filter(user=target_user, is_active=True).update(is_active=False, end_at=now)

    # Log the action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='unsuspend',
        target_user=target_user,
        reason=reason,
    )

    # Notify the user
    Notification.objects.create(
        recipient=target_user,
        sender=request.user,
        notification_type='mention',
        message='Your suspension has been lifted. Welcome back!'
    )

    messages.success(request, f'Suspension lifted for {target_user.username}.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    return redirect(request.META.get('HTTP_REFERER', 'social:moderation_dashboard'))


@moderator_required
@require_POST
@transaction.atomic
def resolve_report(request, pk):
    """
    Resolve a report as handled.
    Requires resolution notes.
    """
    report = get_object_or_404(SocialReport, pk=pk)
    resolution_notes = request.POST.get('resolution_notes', '').strip()
    action_taken = request.POST.get('action_taken', '').strip()

    if not resolution_notes:
        messages.error(request, 'Resolution notes are required.')
        return redirect('social:report_detail', pk=pk)

    # Update report status
    report.status = 'resolved'
    report.save(update_fields=['status'])

    # Log the action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='resolve_report',
        related_report=report,
        reason=f'Report resolved: {action_taken}\n{resolution_notes}',
    )

    # Notify reporter
    if report.reporter:
        Notification.objects.create(
            recipient=report.reporter,
            sender=request.user,
            notification_type='mention',
            message='Your report has been reviewed and action has been taken. Thank you for helping keep our community safe.'
        )

    messages.success(request, f'Report #{report.id} has been resolved.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    return redirect('social:moderation_reports')


@moderator_required
@require_POST
@transaction.atomic
def dismiss_report(request, pk):
    """
    Dismiss a report as invalid or not actionable.
    """
    report = get_object_or_404(SocialReport, pk=pk)
    reason = request.POST.get('reason', '').strip()

    if not reason:
        messages.error(request, 'Reason for dismissal is required.')
        return redirect('social:report_detail', pk=pk)

    # Update report (use resolved to indicate closure; no 'dismissed' status available)
    report.status = 'resolved'
    report.save(update_fields=['status'])

    # Unflag content if applicable and no other pending/reviewing reports
    if report.reported_post:
        post = report.reported_post
        other_pending = SocialReport.objects.filter(
            reported_post=post,
            status__in=['pending', 'reviewing']
        ).exclude(pk=report.pk).exists()
        if not other_pending:
            post.is_flagged = False
            post.hidden_at = None
            post.save(update_fields=['is_flagged', 'hidden_at'])
    if report.reported_comment:
        comment = report.reported_comment
        other_pending_c = SocialReport.objects.filter(
            reported_comment=comment,
            status__in=['pending', 'reviewing']
        ).exclude(pk=report.pk).exists()
        if not other_pending_c:
            comment.is_flagged = False
            comment.hidden_at = None
            comment.save(update_fields=['is_flagged', 'hidden_at'])

    # Log the action
    ModerationAction.objects.create(
        moderator=request.user,
        action_type='dismiss_report',
        related_report=report,
        reason=reason,
    )

    messages.success(request, f'Report #{report.id} has been dismissed.')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True})

    return redirect('social:moderation_reports')


@moderator_required
def moderation_queue(request):
    """
    Show all flagged content that needs review (posts and comments).
    Combines flagged posts and comments into a unified queue.
    """
    from django.db.models import Q
    from itertools import chain

    # Get filter parameters
    content_type_filter = request.GET.get('type', '')  # 'posts' or 'comments'
    sort_by = request.GET.get('sort', 'newest')

    # Get flagged content
    if content_type_filter == 'posts' or not content_type_filter:
        flagged_posts = Post.objects.filter(
            Q(is_flagged=True) | Q(hidden_at__isnull=False)
        ).select_related('author', 'category').prefetch_related('reports').order_by('-created_at')
    else:
        flagged_posts = Post.objects.none()

    if content_type_filter == 'comments' or not content_type_filter:
        flagged_comments = Comment.objects.filter(
            Q(is_flagged=True) | Q(hidden_at__isnull=False)
        ).select_related('author', 'post').prefetch_related('reports').order_by('-created_at')
    else:
        flagged_comments = Comment.objects.none()

    # Sort options
    if sort_by == 'reports':
        # Sort by number of reports
        flagged_posts = flagged_posts.annotate(
            report_count=Count('reports')
        ).order_by('-report_count', '-created_at')
        flagged_comments = flagged_comments.annotate(
            report_count=Count('reports')
        ).order_by('-report_count', '-created_at')
    elif sort_by == 'oldest':
        flagged_posts = flagged_posts.order_by('created_at')
        flagged_comments = flagged_comments.order_by('created_at')

    # Combine and paginate
    if content_type_filter == 'posts':
        combined_items = list(flagged_posts)
    elif content_type_filter == 'comments':
        combined_items = list(flagged_comments)
    else:
        # Combine both, sort by created_at or hidden_at if present
        def sort_key(x):
            return x.hidden_at or x.created_at
        combined_items = sorted(
            chain(flagged_posts, flagged_comments),
            key=sort_key,
            reverse=True
        )

    # Pagination
    paginator = Paginator(combined_items, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stats
    queue_stats = {
        'total_flagged': len(combined_items),
        'flagged_posts': flagged_posts.count(),
        'flagged_comments': flagged_comments.count(),
        'hidden_posts': Post.objects.filter(hidden_at__isnull=False).count(),
        'hidden_comments': Comment.objects.filter(hidden_at__isnull=False).count(),
    }

    context = {
        'page_obj': page_obj,
        'content_type_filter': content_type_filter,
        'sort_by': sort_by,
        'queue_stats': queue_stats,
    }

    return render(request, 'social/moderation/queue.html', context)


@moderator_required
def moderation_users(request):
    """
    View and manage users with moderation issues.
    Shows suspended users, users with warnings, and recently reported users.
    """
    from django.db.models import Count, Q

    # Get filter parameters
    status_filter = request.GET.get('status', '')  # 'suspended', 'warned', 'reported'
    search_query = request.GET.get('search', '')

    # Base queryset
    users = User.objects.select_related('social_profile').annotate(
        report_count=Count('social_reports_received', distinct=True),
        warning_count=Count(
            'actions_against_user',
            filter=Q(actions_against_user__action_type='warn'),
            distinct=True,
        ),
        is_suspended_flag=models.F('social_profile__is_suspended')
    )

    # Apply filters
    if status_filter == 'suspended':
        users = users.filter(social_profile__is_suspended=True)
    elif status_filter == 'warned':
        users = users.filter(actions_against_user__action_type='warn').distinct()
    elif status_filter == 'reported':
        users = users.filter(social_reports_received__isnull=False).distinct()

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )

    # Order by priority (suspended > warnings > reports)
    users = users.order_by(
        '-is_suspended_flag',
        '-warning_count',
        '-report_count',
        '-date_joined'
    )

    # Pagination
    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Stats
    user_stats = {
        'total_users': User.objects.count(),
        'suspended_users': UserProfile.objects.filter(is_suspended=True).count(),
        'warned_users': User.objects.filter(actions_against_user__action_type='warn').distinct().count(),
        'reported_users': User.objects.filter(social_reports_received__isnull=False).distinct().count(),
    }

    context = {
        'page_obj': page_obj,
        'status_filter': status_filter,
        'search_query': search_query,
        'user_stats': user_stats,
    }

    return render(request, 'social/moderation/users.html', context)


@moderator_required
def moderation_logs(request):
    """
    View complete audit log of all moderation actions.
    Filterable by moderator, action type, date range, and search.
    """
    from django.db.models import Q
    from django.utils import timezone

    # Get filter parameters
    moderator_filter = request.GET.get('moderator', '')
    action_type_filter = request.GET.get('action_type', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    search_query = request.GET.get('search', '')

    # Base queryset
    actions = ModerationAction.objects.select_related(
        'moderator',
        'target_user',
        'target_post',
        'target_comment',
        'related_report'
    ).order_by('-created_at')

    # Apply filters
    if moderator_filter:
        actions = actions.filter(moderator__username=moderator_filter)

    if action_type_filter:
        actions = actions.filter(action_type=action_type_filter)

    if date_from:
        try:
            date_from_obj = datetime.strptime(date_from, '%Y-%m-%d')
            actions = actions.filter(created_at__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.strptime(date_to, '%Y-%m-%d')
            actions = actions.filter(created_at__lte=date_to_obj)
        except ValueError:
            pass

    if search_query:
        actions = actions.filter(
            Q(reason__icontains=search_query) |
            Q(moderator__username__icontains=search_query) |
            Q(target_user__username__icontains=search_query)
        )

    # Pagination
    paginator = Paginator(actions, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Moderators for filter dropdown
    moderators = User.objects.filter(
        Q(is_staff=True) | Q(groups__name='Moderators')
    ).distinct().order_by('username')

    # Stats
    from datetime import timedelta as _timedelta
    log_stats = {
        'total_actions': ModerationAction.objects.count(),
        'today_actions': ModerationAction.objects.filter(
            created_at__gte=timezone.now().date()
        ).count(),
        'this_week_actions': ModerationAction.objects.filter(
            created_at__gte=timezone.now() - _timedelta(days=7)
        ).count(),
    }

    context = {
        'page_obj': page_obj,
        'moderator_filter': moderator_filter,
        'action_type_filter': action_type_filter,
        'date_from': date_from,
        'date_to': date_to,
        'search_query': search_query,
        'moderators': moderators,
        'action_types': ModerationAction.ACTION_TYPES,
        'log_stats': log_stats,
    }

    return render(request, 'social/moderation/logs.html', context)
@login_required
@require_POST
def repost_post(request, pk):
    original = get_object_or_404(Post, pk=pk)
    title = f"Shared from @{original.author.username}: {original.title}"
    link = request.build_absolute_uri(reverse('social:post_detail', kwargs={'pk': original.pk}))
    caption = (request.POST.get('caption') or '').strip()
    if caption:
        content = caption
    else:
        excerpt = (original.content[:180] + '...') if original.content and len(original.content) > 180 else (original.content or '')
        content = f"Shared from @{original.author.username}\n\n{excerpt}"
    new_post = Post.objects.create(title=title, content=content, author=request.user, category=original.category, repost_of=original)
    # Attach media from original post
    if original.image:
        new_post.image = original.image
        new_post.save(update_fields=['image'])
    for img in original.images.all():
        PostImage.objects.create(post=new_post, image=img.image)
    for vid in original.videos.all():
        PostVideo.objects.create(post=new_post, file=vid.file)
    # Notify original author
    if original.author != request.user:
        try:
            Notification.objects.create(
                recipient=original.author,
                sender=request.user,
                notification_type='share',
                post=new_post,
                message=f"shared your post"
            )
        except Exception:
            pass
    redirect_target = request.POST.get('redirect', '')
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'post_id': new_post.pk})
    messages.success(request, 'Post shared successfully!')
    return redirect('social:feed')
