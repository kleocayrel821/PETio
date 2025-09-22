from rest_framework import serializers
from .models import PetProfile, FeedingLog, FeedingSchedule, PendingCommand
import logging

logger = logging.getLogger(__name__)


class PetProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = PetProfile
        fields = ["id", "name", "weight", "portion_size"]


class FeedingLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedingLog
        fields = ["id", "timestamp", "source", "portion_dispensed"]


class PendingCommandSerializer(serializers.ModelSerializer):
    class Meta:
        model = PendingCommand
        fields = ["id", "command", "portion_size", "status", "created_at", 
                 "processed_at", "error_message"]
        read_only_fields = ["id", "created_at", "processed_at"]


class FeedingScheduleSerializer(serializers.ModelSerializer):
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