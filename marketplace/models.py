"""
Marketplace domain models: Category, Listing, MessageThread, Message, Transaction, Report.

Minimal schema to support browsing, listing management, messaging, lightweight transactions,
and reporting. Includes sensible indexes for common queries and default ordering.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()


class TimeStampedModel(models.Model):
    """Abstract base model that adds created_at and updated_at timestamps."""
    created_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    """Listing taxonomy used for browsing and filtering."""
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"], name="idx_category_slug"),
            models.Index(fields=["name"], name="idx_category_name"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.name


class ListingStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PENDING = "pending", "Pending Approval"
    REJECTED = "rejected", "Rejected"
    ACTIVE = "active", "Active"
    RESERVED = "reserved", "Reserved"
    SOLD = "sold", "Sold"
    ARCHIVED = "archived", "Archived"


class Listing(TimeStampedModel):
    """A marketplace item created by a seller and discoverable by buyers."""
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="listings")
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, blank=True, related_name="listings"
    )
    title = models.CharField(max_length=160, db_index=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantity = models.PositiveIntegerField(default=1)

    # Minimal: one primary image to start. Can be extended with a related Image model later.
    main_image = models.ImageField(upload_to="listings/%Y/%m/", blank=True, null=True)

    status = models.CharField(
        max_length=16, choices=ListingStatus.choices, default=ListingStatus.PENDING, db_index=True
    )
    # Moderation fields
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_listings"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_reason = models.CharField(max_length=240, blank=True)
    # Rejection audit fields
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="listings_rejected"
    )
    rejected_reason_code = models.CharField(
        max_length=32,
        blank=True,
        choices=[
            ("spam", "Spam or Promotional Content"),
            ("prohibited_item", "Prohibited or Unsafe Item"),
            ("missing_info", "Missing Required Information"),
            ("inappropriate_content", "Inappropriate Content"),
            ("fake_photos", "Misleading or Stock Photos"),
            ("pricing_issue", "Unreasonable Pricing"),
            ("other", "Other"),
        ],
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("can_approve_listing", "Can approve/reject listings"),
            ("can_view_analytics", "Can view analytics"),
        ]
        indexes = [
            models.Index(fields=["status"], name="idx_listing_status"),
            models.Index(fields=["category", "status"], name="idx_listing_cat_status"),
            models.Index(fields=["seller", "status"], name="idx_listing_seller_status"),
            models.Index(fields=["price"], name="idx_listing_price"),
            models.Index(fields=["-created_at"], name="idx_listing_created_desc"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.title} ({self.get_status_display()})"


class ListingPhoto(TimeStampedModel):
    """Additional photos for a listing."""
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField(upload_to="listings/%Y/%m/", blank=False, null=False)
    caption = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["listing"], name="idx_listingphoto_listing"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Photo #{self.id} for {self.listing_id}"


class ThreadStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    ARCHIVED = "archived", "Archived"


class MessageThread(TimeStampedModel):
    """Conversation thread between buyer and seller centered on a listing."""
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="threads")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="buy_threads")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sell_threads")

    status = models.CharField(
        max_length=12, choices=ThreadStatus.choices, default=ThreadStatus.ACTIVE, db_index=True
    )
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-last_message_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["listing", "buyer", "seller"], name="uq_thread_listing_parties"
            )
        ]
        indexes = [
            models.Index(fields=["listing"], name="idx_thread_listing"),
            models.Index(fields=["status"], name="idx_thread_status"),
            models.Index(fields=["-last_message_at"], name="idx_thread_last_msg_desc"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Thread #{self.id} on {self.listing.title}"


class Message(TimeStampedModel):
    """An individual message within a thread."""
    thread = models.ForeignKey(MessageThread, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    content = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["thread", "created_at"], name="idx_msg_thread_created"),
            models.Index(fields=["sender"], name="idx_msg_sender"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Msg #{self.id} in Thread #{self.thread_id}"


class TransactionStatus(models.TextChoices):
    PROPOSED = "proposed", "Proposed"
    CONFIRMED = "confirmed", "Confirmed"
    AWAITING_PAYMENT = "awaiting_payment", "Awaiting Payment"
    PAID = "paid", "Paid"
    COMPLETED = "completed", "Completed"
    CANCELED = "canceled", "Canceled"


class Transaction(TimeStampedModel):
    """Lightweight record of an agreed exchange for a listing."""
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="transactions")
    buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="purchases")
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sales")

    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PROPOSED,
        db_index=True,
    )
    meetup_time = models.DateTimeField(null=True, blank=True)
    meetup_place = models.CharField(max_length=200, blank=True)
    # Timezone and reschedule tracking for meetup logistics
    meetup_timezone = models.CharField(max_length=64, blank=True)
    reschedule_reason = models.TextField(blank=True)

    # Offline payment tracking
    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        OTHER = "other", "Other"

    payment_method = models.CharField(
        max_length=20, choices=PaymentMethod.choices, null=True, blank=True
    )
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_proof = models.FileField(upload_to="payments/%Y/%m/", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("can_manage_transactions", "Can manage marketplace transactions"),
        ]
        indexes = [
            models.Index(fields=["listing", "status"], name="idx_tx_listing_status"),
            models.Index(fields=["buyer"], name="idx_tx_buyer"),
            models.Index(fields=["seller"], name="idx_tx_seller"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Txn #{self.id} for {self.listing.title} ({self.get_status_display()})"


class PurchaseRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    NEGOTIATING = "negotiating", "Negotiating"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"
    CANCELED = "canceled", "Canceled"


class PurchaseRequest(TimeStampedModel):
    """Manual purchase request initiated by a buyer for a listing."""
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="purchase_requests")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="purchase_requests")
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="incoming_requests")

    status = models.CharField(
        max_length=16, choices=PurchaseRequestStatus.choices, default=PurchaseRequestStatus.PENDING, db_index=True
    )
    message = models.TextField(blank=True)
    # Negotiation fields
    offer_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    quantity = models.PositiveIntegerField(null=True, blank=True)
    counter_offer = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    canceled_reason = models.TextField(blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    transaction = models.OneToOneField(
        'Transaction', on_delete=models.SET_NULL, null=True, blank=True, related_name="purchase_request"
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller", "status"], name="idx_pr_seller_status"),
            models.Index(fields=["buyer", "status"], name="idx_pr_buyer_status"),
            models.Index(fields=["listing", "status"], name="idx_pr_listing_status"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Request #{self.id} on {self.listing.title} ({self.get_status_display()})"


class RequestMessage(TimeStampedModel):
    """Message tied to a PurchaseRequest for in-app communication."""
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="request_messages")
    content = models.TextField()
    read_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["request", "created_at"], name="idx_reqmsg_request_created"),
            models.Index(fields=["author"], name="idx_reqmsg_author"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"ReqMsg #{self.id} for Request #{self.request_id}"


class LogAction(models.TextChoices):
    BUYER_REQUEST = "buyer_request", "Buyer Request"
    SELLER_ACCEPT = "seller_accept", "Seller Accepted"
    SELLER_REJECT = "seller_reject", "Seller Rejected"
    SELLER_NEGOTIATE = "seller_negotiate", "Seller Negotiated"
    OFFER_SUBMITTED = "offer_submitted", "Offer Submitted"
    OFFER_COUNTERED = "offer_countered", "Offer Countered"
    OFFER_ACCEPTED = "offer_accepted", "Offer Accepted"
    OFFER_REJECTED = "offer_rejected", "Offer Rejected"
    MEETUP_PROPOSED = "meetup_proposed", "Meetup Proposed"
    MEETUP_UPDATED = "meetup_updated", "Meetup Updated"
    MEETUP_CONFIRMED = "meetup_confirmed", "Meetup Confirmed"
    DISPUTE_OPENED = "dispute_opened", "Dispute Opened"
    DISPUTE_RESOLVED = "dispute_resolved", "Dispute Resolved"
    MOD_APPROVE_LISTING = "mod_approve_listing", "Moderator Approved Listing"
    MOD_REJECT_LISTING = "mod_reject_listing", "Moderator Rejected Listing"
    REQUEST_COMPLETED = "request_completed", "Request Completed"
    REQUEST_CANCELED = "request_canceled", "Request Canceled"


class TransactionLog(TimeStampedModel):
    """Audit log of actions taken on a purchase request."""
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="logs")
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="action_logs")
    action = models.CharField(max_length=40, choices=LogAction.choices, db_index=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["request", "action"], name="idx_txlog_request_action"),
            models.Index(fields=["actor"], name="idx_txlog_actor"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Log #{self.id} {self.action} on Req #{self.request_id}"


class NotificationType(models.TextChoices):
    REQUEST_CREATED = "request_created", "Request Created"
    STATUS_CHANGED = "status_changed", "Status Changed"
    MESSAGE_POSTED = "message_posted", "Message Posted"
    SYSTEM_BROADCAST = "system_broadcast", "System Broadcast"


class Notification(TimeStampedModel):
    """Simple in-app notification for a user.

    Supports unread tracking and optional association to a purchase request or listing.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=32, choices=NotificationType.choices, db_index=True)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    unread = models.BooleanField(default=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    related_request = models.ForeignKey(
        PurchaseRequest, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    related_listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    email_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "unread"], name="idx_notification_user_unread"),
            models.Index(fields=["type"], name="idx_notification_type"),
        ]
        permissions = [
            ("can_broadcast_notifications", "Can broadcast notifications"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Notif #{self.id} to {getattr(self.user, 'username', self.user_id)}: {self.title}"

    # Convenience methods for read state management
    def mark_as_read(self):
        """Mark notification as read now and update unread flag."""
        from django.utils import timezone as dj_tz
        self.read_at = dj_tz.now()
        self.unread = False

    def mark_as_unread(self):
        """Mark notification as unread (clear read_at)."""
        self.read_at = None
        self.unread = True


class SellerRating(TimeStampedModel):
    """Rating left by buyer after completion of a transaction/request."""
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="seller_ratings")
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name="buyer_ratings")
    purchase_request = models.ForeignKey(PurchaseRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name="ratings")
    listing = models.ForeignKey(Listing, on_delete=models.SET_NULL, null=True, blank=True, related_name="ratings")
    score = models.PositiveSmallIntegerField(default=5)
    comment = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["seller"], name="idx_rating_seller"),
            models.Index(fields=["buyer"], name="idx_rating_buyer"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(score__gte=1) & models.Q(score__lte=5), name="ck_rating_score_1_5"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"Rating {self.score} for {self.seller_id} by {self.buyer_id}"


class ReportStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_REVIEW = "in_review", "In Review"
    CLOSED = "closed", "Closed"


class Report(TimeStampedModel):
    """User-submitted report about a listing (or behavior) for moderation."""
    reporter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reports")
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name="reports")
    reason = models.CharField(max_length=120)
    details = models.TextField(blank=True)
    status = models.CharField(
        max_length=10, choices=ReportStatus.choices, default=ReportStatus.OPEN, db_index=True
    )

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("can_moderate_reports", "Can handle user reports"),
        ]
        indexes = [
            models.Index(fields=["listing", "status"], name="idx_report_listing_status"),
            models.Index(fields=["reporter"], name="idx_report_reporter"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Report #{self.id} on {self.listing.title} ({self.get_status_display()})"
