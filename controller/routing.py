from django.urls import path
from .consumers import DeviceStatusConsumer, FeedingLogConsumer

websocket_urlpatterns = [
    path('ws/device-status/', DeviceStatusConsumer.as_asgi()),
    path('ws/feeding-logs/', FeedingLogConsumer.as_asgi()),
]