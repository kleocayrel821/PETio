from django.contrib import admin
from .models import (
    Category,
    Post,
    Comment,
    Like,
    Follow,
    UserProfile,
    Notification,
    Announcement,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "color", "icon", "created_at")
    search_fields = ("name", "description")
    list_filter = ("created_at",)


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "category", "created_at", "is_pinned")
    search_fields = ("title", "content", "author__username")
    list_filter = ("category", "created_at", "is_pinned")
    autocomplete_fields = ("author", "category")


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("post", "author", "content", "created_at", "parent")
    search_fields = ("content", "author__username", "post__title")
    list_filter = ("created_at",)
    autocomplete_fields = ("post", "author", "parent")


@admin.register(Like)
class LikeAdmin(admin.ModelAdmin):
    list_display = ("user", "post", "created_at")
    search_fields = ("user__username", "post__title")
    list_filter = ("created_at",)
    autocomplete_fields = ("user", "post")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ("follower", "following", "created_at")
    search_fields = ("follower__username", "following__username")
    list_filter = ("created_at",)
    autocomplete_fields = ("follower", "following")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "bio", "location", "website", "created_at")
    search_fields = ("user__username", "bio", "location")
    list_filter = ("created_at", "is_private")
    autocomplete_fields = ("user",)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("recipient", "sender", "notification_type", "message", "is_read", "created_at")
    search_fields = ("recipient__username", "sender__username", "message")
    list_filter = ("notification_type", "is_read", "created_at")
    autocomplete_fields = ("recipient", "sender", "post", "comment")


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "start_at", "end_at", "created_at")
    search_fields = ("title", "content")
    list_filter = ("is_active", "created_at")
