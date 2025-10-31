from django.db.models.signals import post_save
from django.dispatch import receiver
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from .models import DeviceStatus, FeedingLog
from .serializers import FeedingLogSerializer

@receiver(post_save, sender=DeviceStatus)
def broadcast_device_status(sender, instance: DeviceStatus, **kwargs):
    layer = get_channel_layer()
    payload = {
        "type": "device_status_event",
        "data": {
            "device_id": instance.device_id,
            "status": instance.status,
            "wifi_rssi": instance.wifi_rssi,
            "uptime": instance.uptime,
            "daily_feeds": instance.daily_feeds,
            "last_feed": instance.last_feed.isoformat() if instance.last_feed else None,
            "last_seen": instance.last_seen.isoformat() if instance.last_seen else None,
        },
    }
    async_to_sync(layer.group_send)("device_status", payload)

@receiver(post_save, sender=FeedingLog)
def broadcast_feeding_log(sender, instance: FeedingLog, **kwargs):
    layer = get_channel_layer()
    data = FeedingLogSerializer(instance).data
    payload = {
        "type": "feeding_log_event",
        "data": data,
    }
    async_to_sync(layer.group_send)("feeding_logs", payload)