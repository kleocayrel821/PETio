from django.urls import path
from controller.routing import websocket_urlpatterns as controller_ws
from marketplace.routing import websocket_urlpatterns as marketplace_ws

# Aggregate websocket URL patterns from apps
websocket_urlpatterns = []
websocket_urlpatterns += controller_ws
websocket_urlpatterns += marketplace_ws
