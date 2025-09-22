from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# Set up DRF routers
router = DefaultRouter()
router.register(r'pets', views.PetProfileViewSet)
router.register(r'logs', views.FeedingLogViewSet)
router.register(r'schedules', views.FeedingScheduleViewSet)
router.register(r'commands', views.PendingCommandViewSet)

urlpatterns = [
    # Web UI
    path("", views.control_panel, name="control_panel"),
    
    # ESP8266 API endpoints
    path("command/", views.get_command, name="get_command"),
    path("feed_now/", views.feed_now, name="feed_now"),
    path("log/", views.log_feed, name="log_feed"),
    # Alias to match firmware expectation for feeding log endpoint
    path("api/feeding-log/", views.log_feed, name="feeding_log"),
    path("command_status/", views.command_status, name="command_status"),
    path("api/check-schedule/", views.check_schedule, name="check_schedule"),
    path("api/device-status/", views.device_status, name="device_status"),
    path("api/remote-command/", views.remote_command, name="remote_command"),
    path("api/stop-feeding/", views.stop_feeding, name="stop_feeding"),
    path("api/calibrate/", views.calibrate, name="calibrate"),
    
    # DRF API endpoints
    path("", include(router.urls)),
]