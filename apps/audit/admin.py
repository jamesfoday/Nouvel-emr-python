from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "action", "actor", "object_type", "object_id", "ip", "created_at")
    search_fields = ("action", "object_type", "object_id", "actor__username", "ip", "user_agent")
    list_filter = ("action", "object_type")
