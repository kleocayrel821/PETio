from django.urls import path
from .consumers import MessageThreadConsumer, RequestMessageConsumer, UserEventsConsumer

websocket_urlpatterns = [
    path("ws/marketplace/thread/<int:thread_id>/", MessageThreadConsumer.as_asgi()),
    path("ws/marketplace/request/<int:request_id>/", RequestMessageConsumer.as_asgi()),
    path("ws/marketplace/events/", UserEventsConsumer.as_asgi()),
]

