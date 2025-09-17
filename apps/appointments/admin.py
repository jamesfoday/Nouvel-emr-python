from django.contrib import admin
from .models import Appointment, Availability  # ensure Appointment already imported

@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("clinician", "weekday", "start_time", "end_time", "slot_minutes", "is_active")
    list_filter = ("clinician", "weekday", "is_active")
