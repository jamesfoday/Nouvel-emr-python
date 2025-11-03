# apps/messaging/models.py
from django.conf import settings
from django.db import models

class Message(models.Model):
    KIND_CHOICES = [("inbox", "Inbox"), ("dm", "Direct")]
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages_in")
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="messages_out")
    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default="inbox")
    subject = models.CharField(max_length=200)
    body = models.TextField(blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
