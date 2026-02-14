from django.contrib import admin
from django.utils import timezone
from .models import PetProfile, FeedingLog, FeedingSchedule, DeviceStatus, Hardware, ControllerSettings


# Register your models here.
admin.site.register(PetProfile)
admin.site.register(FeedingLog)
admin.site.register(FeedingSchedule)
admin.site.register(DeviceStatus)


@admin.register(Hardware)
class HardwareAdmin(admin.ModelAdmin):
    list_display = ("id", "unique_key", "is_paired", "paired_user", "created_at")
    list_filter = ("is_paired",)
    search_fields = ("unique_key", "paired_user__username")
    actions = ["force_unpair", "generate_hardware_10"]

    def force_unpair(self, request, queryset):
        for hw in queryset:
            hw.is_paired = False
            hw.paired_user = None
            hw.save(update_fields=["is_paired", "paired_user", "updated_at"])
    force_unpair.short_description = "Force unpair selected hardware"

    def generate_hardware_10(self, request, queryset):
        for _ in range(10):
            Hardware.objects.create()
    generate_hardware_10.short_description = "Generate 10 hardware records"


@admin.register(ControllerSettings)
class ControllerSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "hardware", "portion_size", "created_at", "updated_at")
    search_fields = ("hardware__unique_key",)
