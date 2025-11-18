"""Social app data models, including posts, comments, profiles,
and Phase 1 moderation models (reports, actions, suspensions).

This file defines core social entities and introduces moderation-related
structures to enable admin and moderator workflows such as reporting content,
taking moderation actions, and temporarily suspending users.
"""

from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils import timezone


class Category(models.Model):
    """Categories for organizing posts"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=7, default='#3B82F6')  # Hex color
    icon = models.CharField(max_length=50, default='fas fa-tag')  # FontAwesome icon
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']
    
    def __str__(self):
        return self.name


class Post(models.Model):
    """Main post model for social media content"""
    title = models.CharField(max_length=200)
    content = models.TextField()
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_posts')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    image = models.ImageField(upload_to='social/posts/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(settings.AUTH_USER_MODEL, through='Like', related_name='liked_posts')
    is_pinned = models.BooleanField(default=False)
    # Moderation flags
    is_flagged = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-is_pinned', '-created_at']
    
    def __str__(self):
        return self.title
    
    def get_absolute_url(self):
        return reverse('social:post_detail', kwargs={'pk': self.pk})
    
    @property
    def like_count(self):
        return self.likes.count()
    
    @property
    def comment_count(self):
        return self.comments.count()


class Like(models.Model):
    """Like relationship between users and posts"""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('user', 'post')
    
    def __str__(self):
        return f"{self.user.username} likes {self.post.title}"


class Comment(models.Model):
    """Comments on posts"""
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_comments')
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Moderation flags
    is_flagged = models.BooleanField(default=False)
    hidden_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['created_at']
    
    def __str__(self):
        return f"Comment by {self.author.username} on {self.post.title}"
    
    @property
    def is_reply(self):
        return self.parent is not None


class Follow(models.Model):
    """Follow relationship between users"""
    follower = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_following_set')
    following = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_followers_set')
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ('follower', 'following')
    
    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class UserProfile(models.Model):
    """Extended user profile for social features"""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_profile')
    bio = models.TextField(max_length=500, blank=True)
    avatar = models.ImageField(upload_to='social/avatars/', blank=True, null=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    birth_date = models.DateField(null=True, blank=True)
    is_private = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Moderation flags
    is_suspended = models.BooleanField(default=False)
    suspended_until = models.DateTimeField(null=True, blank=True)
    suspension_reason = models.CharField(max_length=255, blank=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    @property
    def follower_count(self):
        return Follow.objects.filter(following=self.user).count()
    
    @property
    def following_count(self):
        return Follow.objects.filter(follower=self.user).count()
    
    @property
    def post_count(self):
        return self.user.social_posts.count()


class Notification(models.Model):
    """Notifications for user activities"""
    NOTIFICATION_TYPES = [
        ('like', 'Like'),
        ('comment', 'Comment'),
        ('follow', 'Follow'),
        ('mention', 'Mention'),
    ]
    
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_notifications')
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_sent_notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, null=True, blank=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE, null=True, blank=True)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Notification for {self.recipient.username}: {self.message}"


class Announcement(models.Model):
    """System or admin announcements for the social app"""
    title = models.CharField(max_length=200)
    content = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    start_at = models.DateTimeField(null=True, blank=True)
    end_at = models.DateTimeField(null=True, blank=True)
    link_url = models.URLField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


# =============================
# Moderation Models (Phase 1)
# =============================

class SocialReport(models.Model):
    """User-submitted reports for content or user behavior.

    Supports reporting posts, comments, or users with a type and status
    tracked for moderation workflows.
    """

    REPORT_TYPES = [
        ('spam', 'Spam'),
        ('harassment', 'Harassment'),
        ('inappropriate', 'Inappropriate Content'),
        ('other', 'Other'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewing', 'Under Review'),
        ('resolved', 'Resolved'),
    ]

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='social_reports_made')
    reported_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='social_reports_received')
    reported_post = models.ForeignKey('Post', on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    reported_comment = models.ForeignKey('Comment', on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')

    report_type = models.CharField(max_length=20, choices=REPORT_TYPES)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        target = self.reported_post or self.reported_comment or self.reported_user
        return f"Report({self.get_report_type_display()}) by {self.reporter} on {target}"


class ModerationAction(models.Model):
    """Actions taken by moderators against users or content.

    Actions include deleting/restoring content, warnings, suspensions, and bans.
    """

    ACTION_TYPES = [
        ('delete_post', 'Delete Post'),
        ('delete_comment', 'Delete Comment'),
        ('restore_post', 'Restore Post'),
        ('restore_comment', 'Restore Comment'),
        ('hide_post', 'Hide Post'),
        ('hide_comment', 'Hide Comment'),
        ('warn', 'Warn'),
        ('suspend', 'Suspend'),
        ('ban', 'Ban'),
        ('unsuspend', 'Unsuspend'),
        ('resolve_report', 'Resolve Report'),
        ('dismiss_report', 'Dismiss Report'),
        ('note', 'Note'),
    ]

    moderator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='moderation_actions')
    target_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_against_user')
    target_post = models.ForeignKey('Post', on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_against_post')
    target_comment = models.ForeignKey('Comment', on_delete=models.SET_NULL, null=True, blank=True, related_name='actions_against_comment')
    related_report = models.ForeignKey('SocialReport', on_delete=models.SET_NULL, null=True, blank=True, related_name='actions')

    action_type = models.CharField(max_length=30, choices=ACTION_TYPES)
    reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.moderator} -> {self.action_type}"


class UserSuspension(models.Model):
    """Represents a suspension window for a user, created by a moderator."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='suspensions')
    reason = models.TextField(blank=True)
    start_at = models.DateTimeField(default=timezone.now)
    end_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='suspensions_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_at']

    def __str__(self):
        return f"Suspension({self.user}) active={self.is_active}"

    @property
    def is_current(self):
        """Return True if the suspension window includes now and is active."""
        now = timezone.now()
        if not self.is_active:
            return False
        if self.end_at is not None and now > self.end_at:
            return False
        return now >= self.start_at