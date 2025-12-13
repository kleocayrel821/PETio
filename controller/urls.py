from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from . import device_api

# Set up DRF routers
router = DefaultRouter()
router.register(r'pets', views.PetProfileViewSet)
router.register(r'logs', views.FeedingLogViewSet)
router.register(r'schedules', views.FeedingScheduleViewSet)
router.register(r'commands', views.PendingCommandViewSet)

urlpatterns = [
    # Web UI
    # Make the control panel the default landing page at site root
    path('', views.control_panel, name='home'),
    path('landing/', views.HomeView.as_view(), name='landing'),
    path('schedules-ui/', views.SchedulesView.as_view(), name='schedules_ui'),
    path('history/', views.HistoryView.as_view(), name='history'),
    path('bmi/', views.BMICalculatorView.as_view(), name='bmi_calculator'),
    # Test route to validate unified base + sidebar in Controller
    path('test-base/', views.test_base, name='test_base'),
    # Temporary legacy route to the old control panel (optional; can remove later)
    path('control/', views.control_panel, name='control_panel'),

    # ESP8266 API endpoints
    path("command/", views.get_command, name="get_command"),
    path("feed_now/", views.feed_now, name="feed_now"),
    path("log/", views.log_feed, name="log_feed"),
    # Alias to match firmware expectation for feeding log endpoint
    path("api/feeding-log/", views.log_feed, name="feeding_log"),
    path("command_status/", views.command_status, name="command_status"),
    path("api/check-schedule/", views.check_schedule, name="check_schedule"),
    # Firmware expects non-API prefixed route for schedule check
    path("check-schedule/", views.check_schedule, name="check_schedule_firmware"),
    path("api/device-status/", views.device_status, name="device_status"),
    path("api/remote-command/", views.remote_command, name="remote_command"),
    path("api/stop-feeding/", views.stop_feeding, name="stop_feeding"),
    path("api/calibrate/", views.calibrate, name="calibrate"),

    # New REST-style device endpoints for firmware
    path("api/device/config/", device_api.device_config, name="device_config"),
    path("api/device/command/", device_api.device_command_fetch, name="device_command_fetch"),
    path("api/device/command/ack/", device_api.device_command_ack, name="device_command_ack"),
    path("api/device/feed-command/", device_api.device_feed_command, name="device_feed_command"),
    path("api/device/logs/", device_api.device_logs, name="device_logs"),
    path("api/device/status/", device_api.device_status_heartbeat, name="device_status_heartbeat"),
    path("api/device/acknowledge/", device_api.device_acknowledge, name="device_acknowledge"),
    path("api/health/", views.health, name="health"),
    path("api/client-errors/", views.client_error_log, name="client_error_log"),

    # DRF API endpoints
    path('', include(router.urls)),          # legacy: /logs/, /schedules/, ...
    path('api/', include(router.urls)),      # new: /api/logs/, /api/schedules/, ...
]
