from django.contrib import admin
from .models import PetProfile, FeedingLog, FeedingSchedule, DeviceStatus, Hardware, ControllerSettings


# Register your models here.
admin.site.register(PetProfile)
admin.site.register(FeedingLog)
admin.site.register(FeedingSchedule)
admin.site.register(DeviceStatus)

@admin.register(Hardware)
class HardwareAdmin(admin.ModelAdmin):
    list_display = ("id", "unique_key", "is_paired", "paired_user", "created_at", "updated_at")
    list_filter = ("is_paired",)
    search_fields = ("id", "unique_key", "paired_user__username", "paired_user__email")
    actions = ["force_unpair_selected"]
    def force_unpair_selected(self, request, queryset):
        for hw in queryset:
            try:
                hw.force_unpair()
            except Exception:
                pass
        self.message_user(request, f"Unpaired {queryset.count()} hardware device(s).")
    force_unpair_selected.short_description = "Force unpair selected hardware"

@admin.register(ControllerSettings)
class ControllerSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "hardware", "portion_size", "created_at", "updated_at")
    search_fields = ("hardware__id",)
