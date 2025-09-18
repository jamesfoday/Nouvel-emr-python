# apps/appointments/admin.py
from django.contrib import admin
from .models import Appointment, Availability


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "clinician", "start", "end", "status", "location")
    list_filter = ("status", "clinician", "start")
    search_fields = ("reason", "location", "patient__given_name", "patient__family_name")


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("id", "clinician", "weekday", "start_time", "end_time", "slot_minutes", "is_active")
    list_filter = ("weekday", "clinician", "is_active")
    search_fields = ("clinician__username",)
