from django.contrib import admin
from .models import Document

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "patient", "clinician", "kind", "content_type", "created_at")
    list_filter = ("kind", "clinician", "content_type")
    search_fields = ("title", "patient__first_name", "patient__last_name")
    autocomplete_fields = ("patient", "clinician")
