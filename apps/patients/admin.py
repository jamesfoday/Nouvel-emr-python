from django.contrib import admin
from .models import Patient


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("id", "family_name", "given_name", "date_of_birth", "phone", "email", "external_id")
    search_fields = (
        "family_name",
        "given_name",
        "email",
        "phone",
        "external_id",
    )
    list_filter = ("date_of_birth",)
