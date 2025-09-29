from django.contrib import admin

from .models import (
    Category,
    Listing,
    MessageThread,
    Message,
    Transaction,
    Report,
    ListingStatus,
)


# Category admin: basic management of taxonomy
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "created_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    ordering = ("name",)


# Listing admin: quick inspection of key commercial fields
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "price",
        "quantity",
        "status",
        "category",
        "seller",
        "created_at",
    )
    list_filter = ("status", "category")
    search_fields = ("title", "description", "seller__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("seller", "category")

    # Admin action to quickly mark selected listings as Active
    def mark_active(self, request, queryset):
        """Admin action: set selected listings to Active status."""
        updated = queryset.update(status=ListingStatus.ACTIVE)
        self.message_user(request, f"Marked {updated} listing(s) as Active.")

    mark_active.short_description = "Mark selected listings as Active"
    actions = ["mark_active"]


# Messaging admin: threads and messages
class MessageThreadAdmin(admin.ModelAdmin):
    list_display = ("listing", "buyer", "seller", "status", "last_message_at")
    list_filter = ("status",)
    search_fields = ("listing__title", "buyer__username", "seller__username")
    date_hierarchy = "last_message_at"
    raw_id_fields = ("listing", "buyer", "seller")


class MessageAdmin(admin.ModelAdmin):
    list_display = ("thread", "sender", "short_content", "created_at")
    search_fields = ("content", "sender__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("thread", "sender")

    def short_content(self, obj):
        """Return a truncated preview of the message content for list display."""
        return (obj.content or "")[:80]

    short_content.short_description = "Content"


# Transaction admin: lightweight records of exchanges
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("listing", "buyer", "seller", "status", "meetup_time", "created_at")
    list_filter = ("status",)
    search_fields = ("listing__title", "buyer__username", "seller__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("listing", "buyer", "seller")


# Report admin: moderation of user-submitted reports
class ReportAdmin(admin.ModelAdmin):
    list_display = ("listing", "reporter", "status", "reason", "created_at")
    list_filter = ("status",)
    search_fields = ("listing__title", "reporter__username", "reason")
    date_hierarchy = "created_at"
    raw_id_fields = ("listing", "reporter")


# Register all marketplace models
admin.site.register(Category, CategoryAdmin)
admin.site.register(Listing, ListingAdmin)
admin.site.register(MessageThread, MessageThreadAdmin)
admin.site.register(Message, MessageAdmin)
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(Report, ReportAdmin)
