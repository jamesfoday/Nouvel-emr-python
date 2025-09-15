from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta
import secrets


class User(AbstractUser):
    # Lightweight display name; extend with 2FA/org binding later.
    display_name = models.CharField(max_length=150, blank=True, default="")

    def __str__(self) -> str:  # type: ignore[override]
        return self.display_name or self.username


class Invite(models.Model):
    # invite token instead of opening registration.
    email = models.EmailField()
    role = models.ForeignKey("rbac.Role", on_delete=models.PROTECT)
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="invites_sent"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    @property
    def is_valid(self) -> bool:
        return self.accepted_at is None and timezone.now() < self.expires_at

    def __str__(self) -> str:
        return f"{self.email} → {self.role} (valid: {self.is_valid})"
