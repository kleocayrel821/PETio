from rest_framework import serializers
from .models import PetProfile, FeedingLog, FeedingSchedule, PendingCommand, Hardware, ControllerSettings
import logging

logger = logging.getLogger(__name__)


class PetProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetProfile
        fields = ["id", "name", "weight", "portion_size"]


class FeedingLogSerializer(serializers.ModelSerializer):
    """Serializer for FeedingLog used by web UI and firmware.
    Adds compatibility fields expected by the current frontend templates:
    - amount: alias of portion_dispensed (read-only)
    - action: normalized action string used by home/history views
    - success: boolean indicating successful dispense (derived)
    - feed_type: normalized type for UI filters/labels (manual/automatic/scheduled)
    """
    # Provide 'amount' as alias to 'portion_dispensed' for frontend compatibility
    amount = serializers.FloatField(source='portion_dispensed', read_only=True)
    # Computed/derived fields for UI
    action = serializers.SerializerMethodField(read_only=True)
    success = serializers.SerializerMethodField(read_only=True)
    feed_type = serializers.SerializerMethodField(read_only=True)

    def get_action(self, obj: FeedingLog) -> str:
        """Map the log source to a UI-friendly action string.
        Frontend expects 'feed' for manual/remote/button/esp and 'scheduled' for schedules.
        Defaults to 'feed' when unknown.
        """
        src = (obj.source or "").lower()
        if src in ('schedule', 'scheduled'):
            return 'scheduled'
        # Treat any other sources (web, button, remote_command, esp, etc.) as manual feed action
        return 'feed'

    def get_feed_type(self, obj: FeedingLog) -> str:
        """Normalize source into UI feed_type categories.
        - manual_button -> manual
        - automatic_button or remote_command/web -> automatic
        - schedule/scheduled -> scheduled
        Fallback to 'manual' when unknown to avoid breaking filters.
        """
        src = (obj.source or "").lower()
        if src in ('schedule', 'scheduled'):
            return 'scheduled'
        if src in ('automatic_button', 'remote_command', 'web', 'esp', 'serial_command'):
            return 'automatic'
        if src in ('manual_button', 'button', 'manual'):
            return 'manual'
        return 'manual'

    def get_success(self, obj: FeedingLog) -> bool:
        """Infer success from the dispensed amount.
        If portion_dispensed is greater than 0, consider it a success.
        """
        try:
            return float(obj.portion_dispensed) > 0
        except Exception:
            return False

    class Meta:
        model = FeedingLog
        fields = ["id", "timestamp", "source", "portion_dispensed", "amount", "action", "success", "feed_type", "device_id"]


class PendingCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingCommand
        fields = ["id", "command", "portion_size", "status", "created_at", 
                 "processed_at", "error_message", "device_id"]
        read_only_fields = ["id", "created_at", "processed_at"]


class FeedingScheduleSerializer(serializers.ModelSerializer):
    def validate_portion_size(self, value):
        try:
            v = float(value)
        except Exception:
            raise serializers.ValidationError("Invalid portion size.")
        if v < 1 or v > 100:
            raise serializers.ValidationError("Portion must be between 1 and 100 grams.")
        return v
    def to_representation(self, instance):
        rep = super().to_representation(instance)
        # Keep output time in 24-hour format for stability (HH:MM:SS)
        t = instance.time
        rep["time"] = f"{t.hour:02d}:{t.minute:02d}:00"
        return rep

    def to_internal_value(self, data):
        """Accept hybrid time formats:
        - "HH:MM AM/PM" (12-hour)
        - "H:MM AM/PM" (12-hour single-digit hour)
        - "HH:MM:SS AM/PM" (12-hour with seconds)
        - "HH:MM" (24-hour)
        - "HH:MM:SS" (24-hour with seconds)
        If parsing fails, default to 08:00 to avoid breaking legacy inputs per project decision.
        Values are stored as Django TimeField in 24-hour time.
        """
        value = data.get("time")
        if isinstance(value, str):
            val = value.strip()
            from datetime import time
            import re
            # 12-hour format with optional seconds and AM/PM
            m12 = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)$", val, re.IGNORECASE)
            if m12:
                hour = int(m12.group(1))
                minute = int(m12.group(2))
                ampm = m12.group(4).upper()
                if hour < 1 or hour > 12 or minute > 59:
                    raise serializers.ValidationError({"time": "Invalid 12-hour time."})
                if ampm == "PM" and hour != 12:
                    hour += 12
                if ampm == "AM" and hour == 12:
                    hour = 0
                data = data.copy()
                data["time"] = time(hour, minute)
                return super().to_internal_value(data)
            # 24-hour HH:MM[:SS]
            m24 = re.match(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$", val)
            if m24:
                hour = int(m24.group(1))
                minute = int(m24.group(2))
                if hour > 23 or minute > 59:
                    raise serializers.ValidationError({"time": "Invalid 24-hour time."})
                data = data.copy()
                data["time"] = time(hour, minute)
                return super().to_internal_value(data)
            # Fallback: default to 08:00 per confirmed policy for unparseable legacy inputs
            logger.warning(f"FeedingScheduleSerializer: unrecognized time format '{val}', defaulting to 08:00")
            data = data.copy()
            data["time"] = time(8, 0)
            return super().to_internal_value(data)
        return super().to_internal_value(data)

    class Meta:
        model = FeedingSchedule
        fields = '__all__'


class HardwareSerializer(serializers.ModelSerializer):
    paired_user = serializers.SerializerMethodField()
    class Meta:
        model = Hardware
        fields = ["id", "unique_key", "is_paired", "paired_user", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
    def get_paired_user(self, obj):
        u = getattr(obj, "paired_user", None)
        if not u:
            return None
        return {"id": u.id, "username": getattr(u, "username", ""), "email": getattr(u, "email", "")}


class ControllerSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ControllerSettings
        fields = ["id", "hardware", "feeding_schedule", "portion_size", "config", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]
    def validate_portion_size(self, value):
        try:
            v = float(value)
        except Exception:
            raise serializers.ValidationError("Invalid portion size.")
        if v < 1 or v > 100:
            raise serializers.ValidationError("Portion must be between 1 and 100 grams.")
        return v
