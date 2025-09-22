from django.contrib import admin
from .models import PetProfile, FeedingLog, FeedingSchedule


# Register your models here.
admin.site.register(PetProfile)
admin.site.register(FeedingLog)
admin.site.register(FeedingSchedule)