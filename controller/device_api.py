from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from django.db import transaction
from django.views.decorators.cache import cache_page

import logging
logger = logging.getLogger(__name__)

from .models import FeedingSchedule, PendingCommand, FeedingLog, DeviceStatus
from .auth_utils import _device_api_key_valid



# ----------------------
# Helpers
# ----------------------

def _resp_ok(message, extra=None):
    data = {"status": "ok", "message": message, "success": True}
    if extra:
        data.update(extra)
    return Response(data)


def _resp_error(message, http_status=status.HTTP_400_BAD_REQUEST):
    return Response({"status": "error", "message": message, "success": False, "error": message}, status=http_status)


# ----------------------
# Config endpoint
# ----------------------

@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
@cache_page(15)
def device_config(request):
    """GET /api/device/config/
    Returns schedule configuration JSON and endpoint hints for firmware.
    """
    if not _device_api_key_valid(request):
        return _resp_error("Invalid or missing API key.", http_status=status.HTTP_403_FORBIDDEN)

    try:
        enabled_only = True
        if request.query_params.get('all'):
            enabled_only = False
        qs = FeedingSchedule.objects.all()
        if enabled_only:
            qs = qs.filter(enabled=True)

        schedules = []
        for s in qs:
            schedules.append({
                "id": s.id,
                "time": s.time.strftime('%H:%M'),
                "portion_size": float(s.portion_size),
                "enabled": bool(s.enabled),
                "label": s.label or "",
                "days_of_week": s.days_of_week or ""
            })

        base = request.build_absolute_uri('/')
        extra = {
            "device_id": request.query_params.get('device_id'),
            "poll_interval_sec": 30,
            "endpoints": {
                "config": base + "api/device/config/",
                "command": base + "api/device/command/",
                "logs": base + "api/device/logs/",
                "status": base + "api/device/status/",
                "ack": base + "api/device/command/ack/",
                # Backward-compat endpoints
                "feed_command": base + "api/device/feed-command/",
                "ack_legacy": base + "api/device/acknowledge/",
            },
            "schedules": schedules
        }
        return _resp_ok("configuration", extra)
    except Exception as e:
        logger.exception("device_config failed")
        return _resp_error(str(e), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ----------------------
# Command fetch (unified)
# ----------------------

@api_view(["GET"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_command_fetch(request):
    """GET /api/device/command/
    Returns next pending command for the given device_id, marks processing.
    """
    if not _device_api_key_valid(request):
        return _resp_error("Invalid or missing API key.", http_status=status.HTTP_403_FORBIDDEN)

    try:
        device_id = request.query_params.get('device_id') or getattr(settings, 'DEVICE_ID', 'feeder-1')
        with transaction.atomic():
            cmd = (
                PendingCommand.objects.select_for_update(skip_locked=True)
                .filter(status='pending', device_id=device_id)
                .order_by('created_at')
                .first()
            )
            if not cmd:
                return _resp_ok("no pending", {"has_command": False})
            cmd.mark_processing()
            return _resp_ok("command", {
                "has_command": True,
                "command_id": cmd.id,
                "command": cmd.command,
                "portion_size": float(cmd.portion_size) if cmd.portion_size is not None else None,
                "created_at": cmd.created_at.isoformat(),
            })
    except Exception as e:
        logger.exception("device_command_fetch failed")
        return _resp_error(str(e), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Backward-compat wrapper
@api_view(["GET"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_feed_command(request):
    """Legacy GET /api/device/feed-command/ -> unified command fetch."""
    return device_command_fetch(request)


# ----------------------
# Command acknowledge (unified)
# ----------------------

@api_view(["POST"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_command_ack(request):
    """POST /api/device/command/ack/
    Acknowledge completion result for command: completed|failed
    """
    if not _device_api_key_valid(request):
        return _resp_error("Invalid or missing API key.", http_status=status.HTTP_403_FORBIDDEN)

    try:
        command_id = request.data.get('command_id')
        device_id = request.data.get('device_id') or getattr(settings, 'DEVICE_ID', 'feeder-1')
        result = (request.data.get('result') or 'ok').lower()
        if not command_id:
            return _resp_error("command_id is required")
        try:
            cmd = PendingCommand.objects.get(id=command_id)
        except PendingCommand.DoesNotExist:
            return _resp_error("command not found", http_status=status.HTTP_404_NOT_FOUND)

        # Ensure device scoping captured
        if device_id and cmd.device_id != device_id:
            cmd.device_id = device_id

        if result in ("ok", "completed", "success"):
            cmd.mark_completed()
        else:
            cmd.mark_failed(request.data.get('error_message', ''))

        # Touch DeviceStatus
        ds, _ = DeviceStatus.objects.get_or_create(device_id=device_id)
        from django.utils import timezone
        ds.last_seen = timezone.now()
        ds.last_feed = timezone.now()
        ds.daily_feeds = (ds.daily_feeds or 0) + (1 if cmd.status == 'completed' else 0)
        ds.save()

        return _resp_ok("acknowledged", {"command_id": cmd.id, "result": cmd.status})
    except Exception as e:
        logger.exception("device_command_ack failed")
        return _resp_error(str(e), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Backward-compat wrapper
@api_view(["POST"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_acknowledge(request):
    """Legacy POST /api/device/acknowledge/ -> unified command ack."""
    return device_command_ack(request)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_logs(request):
    """POST /api/device/logs/
    Receives logs from the ESP8266: { logs: [ {timestamp, portion_dispensed, source} ] } or single log body.
    """
    if not _device_api_key_valid(request):
        return _resp_error("Invalid or missing API key.", http_status=status.HTTP_403_FORBIDDEN)

    payload = request.data or {}
    logs = payload.get('logs')
    created = 0
    try:
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone
        device_id = payload.get('device_id') or getattr(settings, 'DEVICE_ID', 'feeder-1')
        def save_one(item):
            nonlocal created
            ts = item.get('timestamp')
            portion = item.get('portion_dispensed')
            source = (item.get('source') or 'esp').strip()
            dt = None
            if ts:
                dt = parse_datetime(ts)
            if dt is None:
                dt = timezone.now()
            try:
                portion_val = float(portion) if portion is not None else 0.0
            except Exception:
                portion_val = 0.0
            FeedingLog.objects.create(timestamp=dt, portion_dispensed=portion_val, source=source, device_id=device_id)
            created += 1

        if isinstance(logs, list):
            for item in logs:
                save_one(item or {})
        else:
            save_one(payload)
        return _resp_ok("logs recorded", {"created": created})
    except Exception as e:
        logger.exception("device_logs failed")
        return _resp_error(str(e), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_status_heartbeat(request):
    """POST /api/device/status/
    Heartbeat from device with telemetry. Mirrors behavior of existing device_status POST.
    """
    if not _device_api_key_valid(request):
        return _resp_error("Invalid or missing API key.", http_status=status.HTTP_403_FORBIDDEN)

    try:
        from django.utils import timezone
        device_id = request.data.get("device_id") or getattr(settings, 'DEVICE_ID', 'feeder-1')
        if not device_id:
            return _resp_error("device_id is required")

        wifi_rssi = request.data.get("wifi_rssi")
        uptime = request.data.get("uptime")
        daily_feeds = request.data.get("daily_feeds")
        last_feed = request.data.get("last_feed")
        error_message = request.data.get("error_message", "")

        def to_int(val, default=None):
            try:
                return int(val)
            except Exception:
                return default

        wifi_rssi = to_int(wifi_rssi)
        uptime = to_int(uptime)
        daily_feeds = to_int(daily_feeds, default=0) or 0

        parsed_last_feed = None
        if last_feed:
            from django.utils.dateparse import parse_datetime
            parsed_last_feed = parse_datetime(last_feed)

        ds, _ = DeviceStatus.objects.get_or_create(device_id=device_id)
        ds.last_seen = timezone.now()
        ds.wifi_rssi = wifi_rssi
        ds.uptime = uptime
        ds.daily_feeds = daily_feeds
        ds.last_feed = parsed_last_feed
        ds.error_message = error_message
        ds.save()
        return _resp_ok("heartbeat recorded")
    except Exception as e:
        logger.exception("device_status_heartbeat failed")
        return _resp_error(str(e), http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)