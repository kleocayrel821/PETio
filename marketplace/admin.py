from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from .models import (
    Category,
    Listing,
    MessageThread,
    Message,
    Transaction,
    Report,
    ListingStatus,
    PurchaseRequest,
    PurchaseRequestStatus,
    RequestMessage,
    TransactionLog,
    Notification,
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
    list_display = (
        "listing",
        "buyer",
        "seller",
        "status",
        "payment_method",
        "amount_paid",
        "meetup_time",
        "created_at",
    )
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

# Manual purchase requests admin
class PurchaseRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "buyer", "seller", "status", "created_at", "accepted_at", "completed_at")
    # Status, date ranges, and cancellation reason presence
    class HasCanceledReasonFilter(admin.SimpleListFilter):
        title = _("Has cancellation reason")
        parameter_name = "has_canceled_reason"

        def lookups(self, request, model_admin):
            return (("yes", _("Yes")), ("no", _("No")))

        def queryset(self, request, queryset):
            val = self.value()
            if val == "yes":
                return queryset.exclude(canceled_reason="").exclude(canceled_reason__isnull=True)
            if val == "no":
                return queryset.filter(Q(canceled_reason="") | Q(canceled_reason__isnull=True))
            return queryset

    list_filter = (
        "status",
        ("created_at", admin.DateFieldListFilter),
        ("accepted_at", admin.DateFieldListFilter),
        ("completed_at", admin.DateFieldListFilter),
        HasCanceledReasonFilter,
    )
    search_fields = ("listing__title", "buyer__username", "seller__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("listing", "buyer", "seller", "transaction")

    # Meetup details are editable via TransactionAdmin; link via transaction field

    # Admin actions: dispute opened/resolved, and force-cancel requests
    actions = ["open_dispute", "resolve_dispute", "force_cancel_requests"]

    def open_dispute(self, request, queryset):
        from .models import TransactionLog, LogAction
        for pr in queryset:
            TransactionLog.objects.create(
                request=pr,
                actor=request.user,
                action=LogAction.DISPUTE_OPENED,
                note=(f"Dispute opened by admin for request #{pr.id}"),
            )
        self.message_user(request, f"Opened dispute on {queryset.count()} request(s).")

    open_dispute.short_description = "Open dispute for selected requests"

    def resolve_dispute(self, request, queryset):
        from .models import TransactionLog, LogAction
        for pr in queryset:
            TransactionLog.objects.create(
                request=pr,
                actor=request.user,
                action=LogAction.DISPUTE_RESOLVED,
                note=(f"Dispute resolved by admin for request #{pr.id}"),
            )
        self.message_user(request, f"Resolved dispute on {queryset.count()} request(s).")

    resolve_dispute.short_description = "Resolve dispute for selected requests"

    def force_cancel_requests(self, request, queryset):
        from .models import PurchaseRequestStatus, TransactionLog, LogAction
        updated = 0
        for pr in queryset:
            if pr.status != PurchaseRequestStatus.COMPLETED:
                pr.status = PurchaseRequestStatus.CANCELED
                if not pr.canceled_reason:
                    pr.canceled_reason = "Force-canceled by admin"
                pr.save(update_fields=["status", "canceled_reason", "updated_at"])
                TransactionLog.objects.create(
                    request=pr,
                    actor=request.user,
                    action=LogAction.REQUEST_CANCELED,
                    note="Force-canceled by admin",
                )
                updated += 1
        self.message_user(request, f"Force-canceled {updated} request(s).")

    force_cancel_requests.short_description = "Force-cancel selected requests"


class RequestMessageAdmin(admin.ModelAdmin):
    list_display = ("request", "author", "short_content", "created_at")
    search_fields = ("content", "author__username")
    date_hierarchy = "created_at"
    raw_id_fields = ("request", "author")

    def short_content(self, obj):
        return (obj.content or "")[:80]

    short_content.short_description = "Content"


class TransactionLogAdmin(admin.ModelAdmin):
    list_display = ("request", "actor", "action", "created_at")
    list_filter = ("action",)
    search_fields = ("request__listing__title", "actor__username", "action")
    date_hierarchy = "created_at"
    raw_id_fields = ("request", "actor")


class NotificationAdmin(admin.ModelAdmin):
    list_display = ("user", "type", "related_listing", "related_request", "title", "created_at", "read_at")
    list_filter = ("type",)
    search_fields = ("user__username", "title", "body")
    date_hierarchy = "created_at"
    raw_id_fields = ("user", "related_listing", "related_request")


admin.site.register(PurchaseRequest, PurchaseRequestAdmin)
admin.site.register(RequestMessage, RequestMessageAdmin)
admin.site.register(TransactionLog, TransactionLogAdmin)
admin.site.register(Notification, NotificationAdmin)
