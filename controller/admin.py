from django.contrib import admin
from .models import PetProfile, FeedingLog, FeedingSchedule, DeviceStatus, Hardware, ControllerSettings, PairingSession
from django.utils.crypto import get_random_string


# Register your models here.
admin.site.register(PetProfile)
admin.site.register(FeedingLog)
admin.site.register(FeedingSchedule)
admin.site.register(DeviceStatus)


@admin.register(PairingSession)
class PairingSessionAdmin(admin.ModelAdmin):
    list_display = ("hardware", "pin", "claimed", "served", "expires_at", "created_at")
    list_filter = ("claimed", "served")
    search_fields = ("hardware__device_id", "pin")


@admin.register(Hardware)
class HardwareAdmin(admin.ModelAdmin):
    list_display = ("id", "device_id", "unique_key", "is_paired", "paired_user", "created_at", "updated_at")
    list_filter = ("is_paired",)
    search_fields = ("unique_key", "device_id", "paired_user__username", "paired_user__email")
    actions = ["force_unpair", "regenerate_unique_key", "create_unpaired", "rotate_api_key"]

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

    def rotate_api_key(self, request, queryset):
        from django.utils.crypto import get_random_string
        for hw in queryset:
            key = get_random_string(48)
            hw.set_api_key(key)
        self.message_user(request, f"Rotated API key for {queryset.count()} hardware device(s).")
    rotate_api_key.short_description = "Rotate API key for selected hardware"


@admin.register(ControllerSettings)
class ControllerSettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "hardware", "portion_size", "created_at", "updated_at")
    search_fields = ("hardware__unique_key",)
