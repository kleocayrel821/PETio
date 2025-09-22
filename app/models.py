from django.db import models
from django.utils import timezone


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
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.command} - {self.status} ({self.created_at})"
    
    def mark_processing(self):
        """Mark command as being processed"""
        self.status = 'processing'
        self.processed_at = timezone.now()
        self.save()
    
    def mark_completed(self):
        """Mark command as completed"""
        self.status = 'completed'
        if not self.processed_at:
            self.processed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message=""):
        """Mark command as failed with optional error message"""
        self.status = 'failed'
        self.error_message = error_message
        if not self.processed_at:
            self.processed_at = timezone.now()
        self.save()


class PetProfile(models.Model):
    name = models.CharField(max_length=100)
    weight = models.FloatField()
    portion_size = models.FloatField()
    
    def __str__(self):
        return f"{self.name} - {self.weight}kg - {self.portion_size}g"


class FeedingLog(models.Model):
    timestamp = models.DateTimeField(auto_now_add=True)
    portion_dispensed = models.FloatField()
    source = models.CharField(max_length=50)  # e.g. "button", "web"
    
    def __str__(self):
        return f"{self.timestamp} - {self.source} - {self.portion_dispensed}g"


class FeedingSchedule(models.Model):
    time = models.TimeField()
    portion_size = models.FloatField()
    enabled = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.time} - {self.portion_size}g - {self.enabled}"