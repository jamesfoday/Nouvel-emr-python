from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    # I’m logging sensitive access/write paths; this is a minimal shape for now.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=64)
    object_type = models.CharField(max_length=64, blank=True, default="")
    object_id = models.CharField(max_length=64, blank=True, default="")
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["object_type", "object_id", "created_at"])]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} by {self.actor} @ {self.created_at:%Y-%m-%d %H:%M}"
