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
    ACTIVE = "active", "Active"
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
        max_length=16, choices=ListingStatus.choices, default=ListingStatus.ACTIVE, db_index=True
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"], name="idx_listing_status"),
            models.Index(fields=["category", "status"], name="idx_listing_cat_status"),
            models.Index(fields=["seller", "status"], name="idx_listing_seller_status"),
            models.Index(fields=["price"], name="idx_listing_price"),
            models.Index(fields=["-created_at"], name="idx_listing_created_desc"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.title} ({self.get_status_display()})"


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
    COMPLETED = "completed", "Completed"
    CANCELED = "canceled", "Canceled"


class Transaction(TimeStampedModel):
    """Lightweight record of an agreed exchange for a listing."""
    listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="transactions")
    buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="purchases")
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="sales")

    status = models.CharField(
        max_length=12,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PROPOSED,
        db_index=True,
    )
    meetup_time = models.DateTimeField(null=True, blank=True)
    meetup_place = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["listing", "status"], name="idx_tx_listing_status"),
            models.Index(fields=["buyer"], name="idx_tx_buyer"),
            models.Index(fields=["seller"], name="idx_tx_seller"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Txn #{self.id} for {self.listing.title} ({self.get_status_display()})"


class ReportStatus(models.TextChoices):
    OPEN = "open", "Open"
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
        indexes = [
            models.Index(fields=["listing", "status"], name="idx_report_listing_status"),
            models.Index(fields=["reporter"], name="idx_report_reporter"),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"Report #{self.id} on {self.listing.title} ({self.get_status_display()})"
