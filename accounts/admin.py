"""
Admin registrations for accounts app models.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import Profile

User = get_user_model()

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Admin configuration for the custom User model.

    Reuses Django's built-in UserAdmin for consistency, adding extra fields.
    """
    fieldsets = DjangoUserAdmin.fieldsets + (
        (
            "Additional info",
            {
                "fields": (
                    "mobile_number",
                    "age",
                    "marketing_opt_in",
                    "email_marketplace_notifications",
                    "email_on_request_updates",
                    "email_on_messages",
                    "notify_marketplace_notifications",
                    "notify_on_request_updates",
                    "notify_on_messages",
                )
            },
        ),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        (
            "Additional info",
            {
                "fields": (
                    "email",
                    "mobile_number",
                    "age",
                    "marketing_opt_in",
                    "email_marketplace_notifications",
                    "email_on_request_updates",
                    "email_on_messages",
                    "notify_marketplace_notifications",
                    "notify_on_request_updates",
                    "notify_on_messages",
                )
            },
        ),
    )
    list_display = ("username", "email", "is_active", "is_staff", "mobile_number", "age", "date_joined")
    list_filter = DjangoUserAdmin.list_filter + ("marketing_opt_in",)
    search_fields = ("username", "email", "mobile_number")

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    """Admin configuration for Profile model."""
    list_display = ("user", "display_name", "location", "phone", "created_at")
    search_fields = ("user__username", "user__email", "display_name", "location", "phone")
    list_filter = ("created_at",)
    autocomplete_fields = ("user",)