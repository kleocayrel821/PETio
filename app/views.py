from django.shortcuts import render
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework import viewsets, status
from django.db import transaction
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from .models import PetProfile, FeedingLog, FeedingSchedule, PendingCommand, DeviceStatus
from .serializers import PetProfileSerializer, FeedingLogSerializer, FeedingScheduleSerializer, PendingCommandSerializer

import logging
logger = logging.getLogger(__name__)
from django.views.decorators.csrf import csrf_exempt
from rest_framework.pagination import PageNumberPagination
from django.views.generic import TemplateView
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework.filters import OrderingFilter
from rest_framework.decorators import action


# Web UI views
def control_panel(request):
    return render(request, 'app/control_panel.html')

# New Class-Based Views for split UI pages
@method_decorator(ensure_csrf_cookie, name='dispatch')
class HomeView(TemplateView):
    """Landing page: marketing and login/signup."""
    template_name = 'landing.html'

@method_decorator(ensure_csrf_cookie, name='dispatch')
class SchedulesView(TemplateView):
    """Schedules management page: add/edit/delete schedules."""
    template_name = 'app/schedules.html'

@method_decorator(ensure_csrf_cookie, name='dispatch')
class HistoryView(TemplateView):
    """Feeding logs page with filters and pagination."""
    template_name = 'app/history.html'


# API views for ESP8266 communication
@permission_classes([AllowAny])
@authentication_classes([])
@api_view(["GET"])
def get_command(request):
    """Endpoint for ESP8266 to poll for commands - Database-backed system"""
    try:
        # Get the oldest pending command atomically
        with transaction.atomic():
            pending_command = PendingCommand.objects.filter(status='pending').first()
            
            if pending_command:
                # Mark as processing to prevent race conditions
                pending_command.mark_processing()
                
                response_data = {
                    "command": pending_command.command,
                    "command_id": pending_command.id
                }
                
                if pending_command.portion_size is not None:
                    response_data["portion_size"] = pending_command.portion_size
                
                return Response(response_data)
            else:
                # No pending commands
                return Response({"command": None})
                
    except Exception as e:
        return Response(
            {"error": f"Failed to fetch command: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
@csrf_exempt
def feed_now(request):
    """Trigger immediate feeding - Database-backed system
    CSRF-exempt to allow frontend fetch without CSRF cookie issues.
    Logs the request for diagnostics.
    """
    try:
        portion_size = request.data.get("portion_size")
        logger.info(f"feed_now: received request portion_size={portion_size}")
        if portion_size is None:
            # Use default from first pet profile if available
            try:
                pet = PetProfile.objects.first()
                portion_size = pet.portion_size if pet else 10.0
            except:
                portion_size = 10.0  # Default fallback
        
        # Create new pending command in database
        with transaction.atomic():
            # Check if there's already a pending feed command to prevent duplicates
            existing_command = PendingCommand.objects.filter(
                command='feed_now',
                status__in=['pending', 'processing']
            ).first()
            
            if existing_command:
                logger.info(f"feed_now: conflict existing pending command id={existing_command.id} portion={existing_command.portion_size}")
                return Response(
                    {
                        "status": "warning",
                        "message": "Feed command already pending",
                        "command_id": existing_command.id,
                        "portion_size": existing_command.portion_size
                    },
                    status=status.HTTP_409_CONFLICT
                )
            
            # Create new command
            command = PendingCommand.objects.create(
                command='feed_now',
                portion_size=float(portion_size)
            )
            logger.info(f"feed_now: queued command id={command.id} portion={command.portion_size}")
            
            return Response({
                "status": "ok",
                "message": "Feed command queued",
                "command_id": command.id,
                "portion_size": command.portion_size
            })
            
    except Exception as e:
        logger.exception("feed_now: error")
        return Response(
            {"error": f"Failed to queue feed command: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def log_feed(request):
    """Log a feeding event from ESP8266 (accepts firmware payload)"""
    # Normalize firmware payload: duration_ms -> portion_dispensed (seconds), default source
    data = getattr(request, "data", {})
    try:
        # Copy-like behavior while being resilient to non-dict payloads
        if hasattr(data, 'copy'):
            data = data.copy()
        else:
            data = dict(data)
    except Exception:
        data = {}
    
    portion = data.get("portion_dispensed")
    if portion is None:
        duration_ms = data.get("duration_ms")
        if duration_ms is not None:
            try:
                portion = float(duration_ms) / 1000.0
            except Exception:
                portion = None
    source = data.get("source") or "esp"
    
    if portion is None:
        return Response({"error": "portion_dispensed or duration_ms required"}, status=status.HTTP_400_BAD_REQUEST)
    
    normalized = {"portion_dispensed": portion, "source": source}
    serializer = FeedingLogSerializer(data=normalized)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def check_schedule(request):
    """Endpoint for ESP8266 to check if it's time for scheduled feeding with robust duplicate prevention.
    Uses local time for comparison and checks recent logs within the last 10 minutes,
    matching on local hour/minute to avoid timezone mismatches causing repeat triggers.

    Additional guard: server-side cache prevents re-triggering the same schedule minute
    even if logs fail to arrive, with a short TTL.
    """
    try:
        # Use timezone-aware now and convert to local time
        from django.utils import timezone
        from datetime import datetime, timedelta
        from django.core.cache import cache
        
        now_aware = timezone.now()
        local_now = timezone.localtime(now_aware)
        current_time = local_now.time()
        current_time_str = current_time.strftime("%I:%M %p")
        today_date = local_now.date()
        # Current day abbreviation (Mon, Tue, ...)
        current_day_abbr = local_now.strftime("%a")
        
        # Get all enabled schedules
        schedules = FeedingSchedule.objects.filter(enabled=True)
        
        should_feed = False
        feed_portion_size = 10.0  # Default portion size
        triggered_schedule = None
        
        # Pre-fetch recent logs in the last 10 minutes (independent of source)
        recent_logs_qs = FeedingLog.objects.filter(
            timestamp__gte=now_aware - timedelta(minutes=10)
        )
        recent_logs = list(recent_logs_qs)
        
        # Widen the trigger window to 180 seconds to tolerate polling jitter while preventing duplicates
        TRIGGER_WINDOW_SECONDS = 180
        
        # Check if current time matches any schedule (within trigger window)
        for schedule in schedules:
            schedule_time = schedule.time
            # Respect days_of_week selection; default to all days if empty/None
            days = schedule.days_of_week if getattr(schedule, 'days_of_week', None) else ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
            if isinstance(days, list) and current_day_abbr not in days:
                logger.info(
                    f"check_schedule: skip sched_id={schedule.id} (day {current_day_abbr} not in {days})"
                )
                continue
            
            # Create timezone-aware datetime for today's scheduled time using current TZ
            schedule_naive = datetime.combine(today_date, schedule_time)
            schedule_datetime = timezone.make_aware(schedule_naive, timezone.get_current_timezone())
            current_datetime = local_now
            
            time_diff = (current_datetime - schedule_datetime).total_seconds()
            within_window = 0 <= time_diff <= TRIGGER_WINDOW_SECONDS
            
            # Cache key: per schedule, date, and minute
            cache_key = f"sched_triggered:{schedule.id}:{today_date.isoformat()}:{schedule_time.strftime('%H%M')}"
            cache_hit = cache.get(cache_key) is not None
            
            logger.info(
                f"check_schedule: now={current_time_str} day={current_day_abbr} sched_id={schedule.id} sched_time={schedule_time.strftime('%H:%M')} "
                f"diff={time_diff:.2f}s within_window={within_window} cache_hit={cache_hit} label={getattr(schedule, 'label', '')}"
            )
            
            if within_window and not cache_hit:
                # Determine if this specific schedule minute has already triggered today (based on logs)
                already_triggered = False
                for log in recent_logs:
                    log_local = timezone.localtime(log.timestamp)
                    if (
                        log_local.date() == today_date and
                        log_local.hour == schedule_time.hour and
                        log_local.minute == schedule_time.minute
                    ):
                        already_triggered = True
                        break
                
                if not already_triggered:
                    # Set cache to prevent duplicate triggers for this minute
                    cache.set(cache_key, True, timeout=180)  # 3 minutes TTL
                    should_feed = True
                    feed_portion_size = schedule.portion_size
                    triggered_schedule = schedule
                    logger.info(
                        f"check_schedule: TRIGGER schedule_id={schedule.id} time={schedule_time.strftime('%H:%M')} "
                        f"portion={schedule.portion_size} day={current_day_abbr}"
                    )
                    break
        
        # Prepare schedule data for debugging
        schedule_data = []
        for schedule in schedules:
            schedule_data.append({
                "id": schedule.id,
                "time": schedule.time.strftime("%H:%M"),
                "portion_size": schedule.portion_size,
                "enabled": schedule.enabled,
                "days_of_week": getattr(schedule, 'days_of_week', []),
                "label": getattr(schedule, 'label', ""),
            })
        
        response_data = {
            "should_feed": should_feed,
            "portion_size": feed_portion_size,
            "current_time": current_time_str,
            "schedules": schedule_data,
            "count": len(schedule_data)
        }
        
        if triggered_schedule:
            response_data["triggered_schedule_id"] = triggered_schedule.id
            response_data["triggered_schedule_time"] = triggered_schedule.time.strftime("%H:%M")
        
        return Response(response_data)
        
    except Exception as e:
        logger.exception("check_schedule: error")
        return Response(
            {"error": f"Failed to check schedules: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST", "GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def device_status(request):
    """Device status endpoint.
    - POST: Heartbeat from ESP8266 with telemetry. Persists to DeviceStatus and marks online.
    - GET: UI polling. Returns computed status (online/offline/unknown) for given device_id.
    """
    try:
        from django.utils import timezone
        from datetime import timedelta

        TTL_SECONDS = 70  # consider device offline if last_seen is older than this

        if request.method == 'GET':
            device_id = request.query_params.get('device_id') or request.GET.get('device_id')
            if not device_id:
                return Response({"status": "unknown", "message": "device_id is required"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                ds = DeviceStatus.objects.get(device_id=device_id)
            except DeviceStatus.DoesNotExist:
                return Response({"status": "unknown", "device_id": device_id})

            now = timezone.now()
            is_online = bool(ds.last_seen and (now - ds.last_seen) <= timedelta(seconds=TTL_SECONDS))
            computed = 'online' if is_online else 'offline'
            data = {
                "status": computed,
                "device_id": ds.device_id,
                "last_seen": ds.last_seen.isoformat() if ds.last_seen else None,
                "wifi_rssi": ds.wifi_rssi,
                "uptime": ds.uptime,
                "daily_feeds": ds.daily_feeds,
                "last_feed": ds.last_feed.isoformat() if ds.last_feed else None,
                "error_message": ds.error_message,
            }
            return Response(data)

        # POST heartbeat from device
        device_id = request.data.get("device_id")
        if not device_id:
            return Response({"error": "device_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Optional fields
        raw_status = request.data.get("status")  # may be provided by firmware but we compute online via last_seen
        daily_feeds = request.data.get("daily_feeds")
        last_feed = request.data.get("last_feed")
        wifi_rssi = request.data.get("wifi_rssi")
        uptime = request.data.get("uptime")
        error_message = request.data.get("error_message", "")

        # Parse types safely
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
            try:
                # Try ISO8601 first
                from django.utils.dateparse import parse_datetime
                parsed_last_feed = parse_datetime(last_feed)
                if parsed_last_feed and parsed_last_feed.tzinfo is None:
                    parsed_last_feed = timezone.make_aware(parsed_last_feed)
            except Exception:
                parsed_last_feed = None

        now = timezone.now()
        ds, _created = DeviceStatus.objects.get_or_create(device_id=device_id)
        ds.status = 'online' if raw_status in (None, '', 'online') else str(raw_status)
        ds.last_seen = now
        ds.wifi_rssi = wifi_rssi
        ds.uptime = uptime
        ds.daily_feeds = daily_feeds
        if parsed_last_feed:
            ds.last_feed = parsed_last_feed
        ds.error_message = error_message or ""
        ds.save()

        logger.info(f"device_status: heartbeat from {device_id} rssi={wifi_rssi} uptime={uptime}s feeds={daily_feeds}")
        return Response({"status": "ok", "device_id": device_id, "computed_status": "online", "last_seen": now.isoformat()})

    except Exception as e:
        logger.exception("device_status: error")
        return Response({"error": f"Failed to process device status: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([AllowAny])
@authentication_classes([])
def remote_command(request):
    """Check for pending remote commands for ESP8266"""
    try:
        device_id = request.headers.get("Device-ID")
        
        if not device_id:
            return Response(
                {"error": "Device-ID header is required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get pending commands for this device
        pending_commands = PendingCommand.objects.filter(
            status="pending"
        ).order_by("created_at")
        
        if pending_commands.exists():
            command = pending_commands.first()
            return Response({
                "command_id": command.id,
                "command": command.command,
                "portion_size": command.portion_size,
                "created_at": command.created_at.isoformat()
            })
        else:
            return Response({
                "command_id": None,
                "command": "none",
                "message": "No pending commands"
            })
            
    except Exception as e:
        return Response(
            {"error": f"Failed to check remote commands: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def command_status(request):
    """Update command status from ESP8266"""
    try:
        command_id = request.data.get("command_id")
        new_status = request.data.get("status")
        error_message = request.data.get("error_message", "")
        
        if not command_id or not new_status:
            return Response(
                {"error": "command_id and status are required"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            try:
                command = PendingCommand.objects.get(id=command_id)
                
                if new_status == "completed":
                    command.mark_completed()
                elif new_status == "failed":
                    command.mark_failed(error_message)
                else:
                    return Response(
                        {"error": f"Invalid status: {new_status}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                return Response({
                    "status": "ok",
                    "message": f"Command {command_id} marked as {new_status}"
                })
                
            except PendingCommand.DoesNotExist:
                return Response(
                    {"error": f"Command {command_id} not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
                
    except Exception as e:
        return Response(
            {"error": f"Failed to update command status: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# Additional device control endpoints
@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def stop_feeding(request):
    """Queue a stop feeding command for ESP8266"""
    try:
        with transaction.atomic():
            command = PendingCommand.objects.create(
                command='stop_feeding',
                portion_size=None
            )
        return Response({
            "status": "ok",
            "message": "Stop feeding command queued",
            "command_id": command.id
        })
    except Exception as e:
        return Response({"error": f"Failed to queue stop feeding: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([])
def calibrate(request):
    """Queue a calibrate command for ESP8266"""
    try:
        with transaction.atomic():
            command = PendingCommand.objects.create(
                command='calibrate',
                portion_size=None
            )
        return Response({
            "status": "ok",
            "message": "Calibrate command queued",
            "command_id": command.id
        })
    except Exception as e:
        return Response({"error": f"Failed to queue calibrate: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# REST API ViewSets
class PetProfileViewSet(viewsets.ModelViewSet):
    queryset = PetProfile.objects.all()
    serializer_class = PetProfileSerializer
    # Allow read-only without auth, write requires auth
    permission_classes = [IsAuthenticatedOrReadOnly]

# Pagination for Feeding Logs
class FeedingLogPagination(PageNumberPagination):
    """PageNumberPagination for FeedingLog list endpoints."""
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100

    def get_page_size(self, request):
        """Support both 'page_size' and legacy 'limit' query params."""
        limit = request.query_params.get('limit')
        if limit is not None:
            try:
                return min(int(limit), self.max_page_size)
            except Exception:
                pass
        return super().get_page_size(request)

class FeedingLogViewSet(viewsets.ModelViewSet):
    queryset = FeedingLog.objects.order_by("-timestamp")
    serializer_class = FeedingLogSerializer
    permission_classes = [AllowAny]
    # Restrict to read-only methods to avoid unauthenticated writes
    http_method_names = ["get", "head", "options"]
    # Enable server-side pagination for logs endpoint
    pagination_class = FeedingLogPagination
    # Enable ordering via query param, e.g. ?ordering=-timestamp
    filter_backends = [OrderingFilter]
    ordering_fields = ["timestamp", "portion_dispensed", "source"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        """Filter logs by start_date/end_date, feed_type, and search.
        - start_date: include logs with timestamp >= start_date 00:00:00
        - end_date: include logs with timestamp <= end_date 23:59:59.999999
        - feed_type: maps UI values to source categories (manual->[manual_button,button,manual], automatic->[automatic_button,remote_command,web,esp,serial_command], scheduled->[schedule,scheduled]); legacy keys 'button','remote','esp' are also supported
        - search: case-insensitive contains on source
        """
        qs = FeedingLog.objects.order_by("-timestamp")
        params = getattr(self.request, 'query_params', {})
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        feed_type = params.get('feed_type')
        search = params.get('search')
        from datetime import datetime, time
        from django.utils.dateparse import parse_date
        from django.db.models import Q

        if start_date:
            sd = parse_date(start_date)
            if sd:
                start_dt = datetime.combine(sd, time.min)
                qs = qs.filter(timestamp__gte=start_dt)
        if end_date:
            ed = parse_date(end_date)
            if ed:
                # End of day inclusive
                from datetime import timedelta
                end_dt = datetime.combine(ed, time.max)
                qs = qs.filter(timestamp__lte=end_dt)
        if feed_type:
            ft = (feed_type or '').lower()
            category_map = {
                'manual': ['manual_button', 'button', 'manual'],
                'automatic': ['automatic_button', 'remote_command', 'web', 'esp', 'serial_command'],
                'scheduled': ['schedule', 'scheduled'],
                # Legacy/synonyms support
                'button': ['manual_button', 'button'],
                'remote': ['automatic_button', 'remote_command'],
                'esp': ['esp'],
                'web': ['web'],
            }
            sources = category_map.get(ft)
            if sources:
                qs = qs.filter(source__in=sources)
            else:
                qs = qs.filter(source__iexact=ft)
        if search:
            qs = qs.filter(Q(source__icontains=search))
        return qs

    @action(detail=False, methods=['get'], url_path='stats', permission_classes=[AllowAny])
    def stats(self, request):
        """Return aggregate statistics for logs: total feeds, total amount, today's feeds, 30-day average daily amount."""
        qs = self.get_queryset()
        total_feeds = qs.count()
        from django.db.models import Sum
        total_amount = qs.aggregate(total=Sum('portion_dispensed'))['total'] or 0
        from django.utils import timezone
        today = timezone.localdate()
        today_feeds = qs.filter(timestamp__date=today).count()
        from datetime import timedelta
        start_30 = today - timedelta(days=30)
        qs30 = FeedingLog.objects.filter(timestamp__date__gte=start_30, timestamp__date__lte=today)
        total30 = qs30.aggregate(total=Sum('portion_dispensed'))['total'] or 0
        days_with_data = qs30.values('timestamp__date').distinct().count() or 1
        avg_daily = total30 / days_with_data
        return Response({
            'total_feeds': total_feeds,
            'total_amount': round(total_amount, 2),
            'today_feeds': today_feeds,
            'avg_daily': round(avg_daily, 2),
        })

    @action(detail=False, methods=['get'], url_path='export', permission_classes=[AllowAny])
    def export(self, request):
        """Export logs as CSV applying current filters."""
        qs = self.get_queryset()
        from django.http import HttpResponse
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="feeding_logs.csv"'
        writer = csv.writer(response)
        writer.writerow(['timestamp', 'amount_g', 'source'])
        for log in qs:
            writer.writerow([log.timestamp.isoformat(), f"{log.portion_dispensed}", log.source])
        return response

class FeedingScheduleViewSet(viewsets.ModelViewSet):
    queryset = FeedingSchedule.objects.all()
    serializer_class = FeedingScheduleSerializer
    permission_classes = [AllowAny]
    # Use same pagination as logs to return count/results keys expected by frontend
    pagination_class = FeedingLogPagination
    # Enable ordering via query param, e.g. ?ordering=-id or ?ordering=time
    filter_backends = [OrderingFilter]
    ordering_fields = ["id", "time", "portion_size", "enabled"]
    # Default to newest first so recently added schedules show up immediately
    ordering = ["-id"]

    def get_queryset(self):
        """
        Return schedules, optionally filtered by the "enabled" query parameter.
        Accepts enabled=true/false/1/0/yes/no (case-insensitive).
        Ensures default ordering (-id) when no explicit ordering is provided.
        """
        qs = FeedingSchedule.objects.all()
        enabled_param = self.request.query_params.get("enabled")
        if enabled_param is not None:
            val = enabled_param.strip().lower()
            if val in ("true", "1", "yes"):
                qs = qs.filter(enabled=True)
            elif val in ("false", "0", "no"):
                qs = qs.filter(enabled=False)
        # Apply default ordering only if no explicit ordering provided via query params
        if not self.request.query_params.get("ordering") and hasattr(self, "ordering"):
            return qs.order_by(*self.ordering)
        return qs

    @action(detail=False, methods=['get'], url_path='stats', permission_classes=[AllowAny])
    def stats(self, request):
        """Return aggregate statistics for logs: total feeds, total amount, today's feeds, 30-day average daily amount."""
        qs = self.get_queryset()
        total_feeds = qs.count()
        from django.db.models import Sum
        total_amount = qs.aggregate(total=Sum('portion_dispensed'))['total'] or 0
        from django.utils import timezone
        today = timezone.localdate()
        today_feeds = qs.filter(timestamp__date=today).count()
        from datetime import timedelta
        start_30 = today - timedelta(days=30)
        qs30 = FeedingLog.objects.filter(timestamp__date__gte=start_30, timestamp__date__lte=today)
        total30 = qs30.aggregate(total=Sum('portion_dispensed'))['total'] or 0
        days_with_data = qs30.values('timestamp__date').distinct().count() or 1
        avg_daily = total30 / days_with_data
        return Response({
            'total_feeds': total_feeds,
            'total_amount': round(total_amount, 2),
            'today_feeds': today_feeds,
            'avg_daily': round(avg_daily, 2),
        })

    @action(detail=False, methods=['get'], url_path='export', permission_classes=[AllowAny])
    def export(self, request):
        """Export logs as CSV applying current filters."""
        qs = self.get_queryset()
        from django.http import HttpResponse
        import csv
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="feeding_logs.csv"'
        writer = csv.writer(response)
        writer.writerow(['timestamp', 'amount_g', 'source'])
        for log in qs:
            writer.writerow([log.timestamp.isoformat(), f"{log.portion_dispensed}", log.source])
        return response

    def update(self, request, *args, **kwargs):
        """Treat PUT updates as partial to support UI that sends only changed fields (e.g., enabled toggle).
        This fixes schedules CRUD where the frontend uses PUT for partial updates.
        """
        kwargs["partial"] = True
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        """Explicit partial update handler to ensure PATCH works as expected."""
        kwargs["partial"] = True
        return super().partial_update(request, *args, **kwargs)

class PendingCommandViewSet(viewsets.ModelViewSet):
    queryset = PendingCommand.objects.all()
    serializer_class = PendingCommandSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    
    def get_queryset(self):
        """Allow filtering by status"""
        queryset = PendingCommand.objects.all()
        status_filter = self.request.query_params.get('status', None)
        if status_filter is not None:
            queryset = queryset.filter(status=status_filter)
        return queryset