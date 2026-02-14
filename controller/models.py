from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from django.conf import settings
import uuid
import logging

logger = logging.getLogger(__name__)


def default_days_of_week():
    """Return all seven days enabled by default to avoid silent inactivation.
    Values use three-letter English abbreviations.
    """
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class PendingCommand(models.Model):
    """
    Database-backed command system to replace global variables
    Prevents race conditions in concurrent API calls
    """
    COMMAND_CHOICES = [
        ('feed_now', 'Feed Now'),
        ('stop_feeding', 'Stop Feeding'),
        ('calibrate', 'Calibrate Motor'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    command = models.CharField(max_length=20, choices=COMMAND_CHOICES)
    portion_size = models.FloatField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    # New: scope commands to device
    device_id = models.CharField(max_length=64, db_index=True, default='feeder-1')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at'])
        ]
    
    def __str__(self):
        return f"{self.command} - {self.status} ({self.created_at})"
    
    def mark_processing(self):
        """Mark command as being processed"""
        prev = self.status
        self.status = 'processing'
        self.processed_at = timezone.now()
        self.save()
        CommandEvent.objects.create(command=self, from_status=prev, to_status=self.status, device_id=self.device_id)
        logger.info("Command transitioned", extra={"device_id": self.device_id, "command_id": self.id, "status": self.status})

    def mark_completed(self):
        """Mark command as completed"""
        prev = self.status
        self.status = 'completed'
        if not self.processed_at:
            self.processed_at = timezone.now()
        self.save()
        CommandEvent.objects.create(command=self, from_status=prev, to_status=self.status, device_id=self.device_id)
        logger.info("Command transitioned", extra={"device_id": self.device_id, "command_id": self.id, "status": self.status})
    
    def mark_failed(self, error_message=""):
        """Mark command as failed with optional error message"""
        prev = self.status
        self.status = 'failed'
        self.error_message = error_message
        if not self.processed_at:
            self.processed_at = timezone.now()
        self.save()
        CommandEvent.objects.create(command=self, from_status=prev, to_status=self.status, device_id=self.device_id)
        logger.info("Command transitioned", extra={"device_id": self.device_id, "command_id": self.id, "status": self.status})


class PetProfile(models.Model):
    name = models.CharField(max_length=100)
    weight = models.FloatField()
    portion_size = models.FloatField(validators=[MinValueValidator(1), MaxValueValidator(100)])
    
    def __str__(self):
        return f"{self.name} - {self.weight}kg - {self.portion_size}g"


class FeedingLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    portion_dispensed = models.FloatField()
    source = models.CharField(max_length=50)  # e.g. "button", "web"
    # New: scope logs to device
    device_id = models.CharField(max_length=64, db_index=True, default='feeder-1')
    
    def __str__(self):
        return f"{self.timestamp} - {self.source} - {self.portion_dispensed}g"


class FeedingSchedule(models.Model):
    time = models.TimeField()
    # Portion stored in grams; enforce safe range 1-500g with default 25g.
    portion_size = models.FloatField(
        default=25,
        validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    enabled = models.BooleanField(default=True)
    # Optional user label, capped at 20 characters (per requirement)
    label = models.CharField(max_length=20, blank=True, default="")
    # Days-of-week selection stored as JSON array of abbreviations
    days_of_week = models.JSONField(default=default_days_of_week)
    
    def __str__(self):
        return f"{self.time} - {self.portion_size}g - {self.enabled} - {','.join(self.days_of_week or [])}"


class DeviceStatus(models.Model):
    """Tracks the latest status/heartbeat of an ESP8266 device.
    Stores connection info, last seen timestamp, and recent telemetry for UI polling.
    """
    STATUS_CHOICES = [
        ("online", "Online"),
        ("offline", "Offline"),
        ("unknown", "Unknown"),
    ]

    device_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="unknown")
    last_seen = models.DateTimeField(null=True, blank=True)

    # Telemetry fields
    wifi_rssi = models.IntegerField(null=True, blank=True)
    uptime = models.IntegerField(null=True, blank=True)  # seconds
    daily_feeds = models.IntegerField(default=0)
    last_feed = models.DateTimeField(null=True, blank=True)

    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.device_id} - {self.status} ({self.last_seen})"


# New: CommandEvent for lifecycle auditing
class CommandEvent(models.Model):
    command = models.ForeignKey(PendingCommand, on_delete=models.CASCADE, related_name='events')
    from_status = models.CharField(max_length=20, blank=True, default='')
    to_status = models.CharField(max_length=20)
    device_id = models.CharField(max_length=64, db_index=True, default='feeder-1')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['command', 'to_status', 'created_at']),
        ]

    def __str__(self):
        return f"cmd={self.command_id} {self.from_status}->{self.to_status} @ {self.created_at}"


class Hardware(models.Model):
    """Physical hardware controller that can operate standalone and be optionally paired to a user.
    Uses a non-guessable unique_key (UUID v4) for identification to avoid predictable IDs.
    """
    unique_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    is_paired = models.BooleanField(default=False)
    paired_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hardware_devices",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["unique_key"], name="idx_hardware_unique_key"),
            models.Index(fields=["is_paired"], name="idx_hardware_is_paired"),
        ]

    def __str__(self):
        return f"Hardware({self.id}) paired={self.is_paired}"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.is_paired and not self.paired_user:
            raise ValidationError("Paired hardware must have a paired_user set.")
        if not self.is_paired and self.paired_user:
            raise ValidationError("Unpaired hardware cannot reference a paired_user.")

    def pair_to_user(self, user):
        """Pair this hardware to the given user if not already paired by someone else."""
        from django.core.exceptions import ValidationError
        if self.is_paired and self.paired_user_id and self.paired_user_id != getattr(user, "id", None):
            raise ValidationError("Hardware is already paired to another user.")
        self.paired_user = user
        self.is_paired = True
        self.save(update_fields=["paired_user", "is_paired", "updated_at"])

    def force_unpair(self):
        """Admin utility to unpair hardware regardless of current pairing."""
        self.paired_user = None
        self.is_paired = False
        self.save(update_fields=["paired_user", "is_paired", "updated_at"])


class ControllerSettings(models.Model):
    """Configurable settings scoped to a single hardware device.
    Enforced one settings row per hardware via unique constraint.
    """
    hardware = models.ForeignKey(Hardware, on_delete=models.CASCADE, related_name="settings")
    feeding_schedule = models.JSONField(default=list, blank=True)
    portion_size = models.FloatField(
        default=25,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Default portion size in grams (1-100).",
    )
    config = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["hardware"], name="uq_settings_hardware"),
        ]
        indexes = [
            models.Index(fields=["hardware"], name="idx_settings_hardware"),
        ]

    def __str__(self):
        return f"ControllerSettings(hw={self.hardware_id})"
