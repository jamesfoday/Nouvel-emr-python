# apps/labs/admin.py
from django.contrib import admin
from .models import (
    LabCatalog,
    LabOrder,
    Specimen,
    DiagnosticReport,
    Observation,
    ExternalLabResult,  
)

# existing registrations...
admin.site.register(LabCatalog)
admin.site.register(LabOrder)
admin.site.register(Specimen)
admin.site.register(DiagnosticReport)
admin.site.register(Observation)



@admin.register(ExternalLabResult)
class ExternalLabResultAdmin(admin.ModelAdmin):
    list_display  = ("id", "patient", "order", "clinician_to", "status", "created_at")
    list_filter   = ("status", "clinician_to")
    search_fields = ("title", "vendor_name", "patient__first_name", "patient__last_name")



