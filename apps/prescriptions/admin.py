from django.contrib import admin
from .models import Prescription

@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "patient", "clinician", "status", "created_at")
    list_filter = ("status", "clinician")
    search_fields = ("title", "patient__first_name", "patient__last_name")
