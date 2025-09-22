from rest_framework import serializers
from .models import PetProfile, FeedingLog, FeedingSchedule, PendingCommand


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
        # Output time in 24-hour format for firmware compatibility
        time_obj = instance.time
        rep["time"] = f"{time_obj.hour:02d}:{time_obj.minute:02d}:00"
        return rep
    def to_internal_value(self, data):
        # Accept 12-hour format with AM/PM for input
        value = data.get("time")
        if value:
            import re
            match = re.match(r"^(\d{1,2}):(\d{2}):\d{2} (AM|PM)$", value)
            if match:
                hour = int(match.group(1))
                minute = int(match.group(2))
                ampm = match.group(3)
                if ampm == "PM" and hour != 12:
                    hour += 12
                if ampm == "AM" and hour == 12:
                    hour = 0
                from datetime import time
                data = data.copy()
                data["time"] = time(hour, minute)
        return super().to_internal_value(data)
    class Meta:
        model = FeedingSchedule
        fields = '__all__'