from django.contrib import admin
from .models import LabCatalog, LabOrder, Specimen, DiagnosticReport, Observation
admin.site.register([LabCatalog, LabOrder, Specimen, DiagnosticReport, Observation])
