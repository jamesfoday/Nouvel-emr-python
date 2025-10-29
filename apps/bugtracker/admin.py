
from django.contrib import admin
from .models import BugReport

@admin.register(BugReport)
class BugReportAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "severity", "status", "reporter", "assigned_to", "created_at")
    search_fields = ("title", "description", "reporter__username", "assigned_to__username")
    list_filter = ("severity", "status", "created_at")
    autocomplete_fields = ("reporter", "assigned_to")
    readonly_fields = ("created_at", "updated_at")
