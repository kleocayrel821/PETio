from django.contrib import admin
from .models import PetProfile, FeedingLog, FeedingSchedule, DeviceStatus, Hardware, ControllerSettings
from django.utils.crypto import get_random_string


# Register your models here.
admin.site.register(PetProfile)
admin.site.register(FeedingLog)
admin.site.register(FeedingSchedule)
admin.site.register(DeviceStatus)


@admin.register(Hardware)
class HardwareAdmin(admin.ModelAdmin):
    list_display = ("id", "unique_key", "is_paired", "paired_user", "created_at", "updated_at")
    list_filter = ("is_paired",)
    search_fields = ("unique_key", "paired_user__username", "paired_user__email")
    actions = ["force_unpair", "regenerate_unique_key", "create_unpaired"]

    def force_unpair(self, request, queryset):
        for hw in queryset:
            hw.is_paired = False
            hw.paired_user = None
            hw.save(update_fields=["is_paired", "paired_user", "updated_at"])
    force_unpair.short_description = "Force unpair selected hardware"

    def regenerate_unique_key(self, request, queryset):
        import uuid
        for hw in queryset:
            hw.unique_key = uuid.uuid4()
            hw.save(update_fields=["unique_key", "updated_at"])
    regenerate_unique_key.short_description = "Regenerate unique key for selected hardware"

    def create_unpaired(self, request, queryset):
        import uuid
        for _ in range(1):
            Hardware.objects.create(unique_key=uuid.uuid4())
    create_unpaired.short_description = "Create one unpaired hardware"


@admin.register(ControllerSettings)
class ControllerSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "hardware", "portion_size", "created_at", "updated_at")
    search_fields = ("hardware__unique_key",)
