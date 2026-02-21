from django.contrib import admin
from .models import PetProfile, FeedingLog, FeedingSchedule, DeviceStatus


# Register your models here.
admin.site.register(PetProfile)
admin.site.register(FeedingLog)
admin.site.register(FeedingSchedule)
admin.site.register(DeviceStatus)