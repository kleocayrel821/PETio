from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings

import logging
logger = logging.getLogger(__name__)

from .models import FeedingSchedule, PendingCommand, FeedingLog, DeviceStatus

def _device_api_key_valid(request):
    """Validate device API key from header X-API-Key against settings.PETIO_DEVICE_API_KEY if set."""
    expected = getattr(settings, 'PETIO_DEVICE_API_KEY', None)
    if not expected:
        return True
    supplied = request.headers.get('X-API-Key') or request.META.get('HTTP_X_API_KEY')
    return supplied == expected

@api_view(["GET"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_config(request):
    """GET /api/device/config/
    Returns schedule configuration JSON and endpoint hints for firmware.
    """
    if not _device_api_key_valid(request):
        return Response({"status": "error", "message": "invalid api key"}, status=status.HTTP_403_FORBIDDEN)

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
        return Response({
            "status": "ok",
            "message": "configuration",
            "device_id": request.query_params.get('device_id'),
            "poll_interval_sec": 30,
            "endpoints": {
                "config": base + "api/device/config/",
                "feed_command": base + "api/device/feed-command/",
                "logs": base + "api/device/logs/",
                "status": base + "api/device/status/",
                "ack": base + "api/device/acknowledge/",
            },
            "schedules": schedules
        })
    except Exception as e:
        logger.exception("device_config failed")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["GET"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_feed_command(request):
    """GET /api/device/feed-command/
    Returns a pending manual feed command, if any, including portion_size.
    """
    if not _device_api_key_valid(request):
        return Response({"status": "error", "message": "invalid api key"}, status=status.HTTP_403_FORBIDDEN)

    try:
        device_id = request.query_params.get('device_id')
        qs = PendingCommand.objects.filter(status='pending')
        # Optional device_id scoping if provided
        if device_id:
            qs = qs.filter(error_message__icontains=device_id)  # simple scoping if stored; else ignore
        cmd = qs.order_by('created_at').first()
        if not cmd:
            return Response({"status": "ok", "has_command": False})
        data = {
            "status": "ok",
            "has_command": True,
            "command_id": cmd.id,
            "command": cmd.command,
            "portion_size": float(cmd.portion_size) if cmd.portion_size is not None else None,
            "created_at": cmd.created_at.isoformat(),
        }
        return Response(data)
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_logs(request):
    """POST /api/device/logs/
    Receives logs from the ESP8266: { logs: [ {timestamp, portion_dispensed, source} ] } or single log body.
    """
    if not _device_api_key_valid(request):
        return Response({"status": "error", "message": "invalid api key"}, status=status.HTTP_403_FORBIDDEN)

    payload = request.data or {}
    logs = payload.get('logs')
    created = 0
    try:
        from django.utils.dateparse import parse_datetime
        from django.utils import timezone
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
            FeedingLog.objects.create(timestamp=dt, portion_dispensed=portion_val, source=source)
            created += 1

        if isinstance(logs, list):
            for item in logs:
                save_one(item or {})
        else:
            save_one(payload)
        return Response({"status": "ok", "created": created})
    except Exception as e:
        logger.exception("device_logs failed")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_status_heartbeat(request):
    """POST /api/device/status/
    Heartbeat from device with telemetry. Mirrors behavior of existing device_status POST.
    """
    if not _device_api_key_valid(request):
        return Response({"status": "error", "message": "invalid api key"}, status=status.HTTP_403_FORBIDDEN)

    try:
        from django.utils import timezone
        device_id = request.data.get("device_id")
        if not device_id:
            return Response({"status": "error", "message": "device_id is required"}, status=status.HTTP_400_BAD_REQUEST)

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
        return Response({"status": "ok", "message": "heartbeat recorded"})
    except Exception as e:
        logger.exception("device_status_heartbeat failed")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"]) 
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def device_acknowledge(request):
    """POST /api/device/acknowledge/
    ESP8266 acknowledges completion of a feed cycle. Marks PendingCommand processed.
    """
    if not _device_api_key_valid(request):
        return Response({"status": "error", "message": "invalid api key"}, status=status.HTTP_403_FORBIDDEN)

    try:
        from django.utils import timezone
        command_id = request.data.get('command_id')
        device_id = request.data.get('device_id')
        result = (request.data.get('result') or 'ok').lower()

        if not command_id:
            return Response({"status": "error", "message": "command_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cmd = PendingCommand.objects.get(id=command_id)
        except PendingCommand.DoesNotExist:
            return Response({"status": "error", "message": "command not found"}, status=status.HTTP_404_NOT_FOUND)

        cmd.status = 'processed' if result == 'ok' else 'failed'
        cmd.processed_at = timezone.now()
        if device_id:
            # Record device context into error_message for traceability without schema changes
            cmd.error_message = (cmd.error_message or '') + f" | device:{device_id}"
        cmd.save()

        # Touch DeviceStatus
        if device_id:
            ds, _ = DeviceStatus.objects.get_or_create(device_id=device_id)
            ds.last_seen = timezone.now()
            ds.last_feed = timezone.now()
            ds.daily_feeds = (ds.daily_feeds or 0) + 1
            ds.save()

        return Response({"status": "ok", "message": "acknowledged", "command_id": cmd.id, "result": cmd.status})
    except Exception as e:
        logger.exception("device_acknowledge failed")
        return Response({"status": "error", "message": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)