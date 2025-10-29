from __future__ import annotations

from datetime import timedelta
import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
from django.db.models.signals import post_save
from django.dispatch import receiver


class User(AbstractUser):
    """
    Project user model.
    - display_name: lightweight label you can show in UI
    - avatar: stored under MEDIA_ROOT/avatars/
    """
    display_name = models.CharField(max_length=150, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    def __str__(self) -> str:  # type: ignore[override]
        return self.display_name or self.get_full_name() or self.username


class Invite(models.Model):
    """
    Simple invite flow: send token by email; expire after 7 days by default.
    """
    email = models.EmailField()
    role = models.ForeignKey("rbac.Role", on_delete=models.PROTECT)
    token = models.CharField(max_length=64, unique=True, editable=False)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="invites_sent",
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


def receptionist_avatar_path(instance, filename):
    return f"avatars/receptionists/{instance.user_id}/{filename}"


class ReceptionistProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="receptionist",
    )
    avatar = models.ImageField(upload_to=receptionist_avatar_path, blank=True, null=True)
    title = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=120, blank=True)
    location = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)

    def __str__(self):
        return f"ReceptionistProfile({self.user})"


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_receptionist_profile(sender, instance, created, **kwargs):
    # Adjust the condition to your rules (e.g., user in "Reception" group).
    if created and getattr(instance, "is_staff", False):
        ReceptionistProfile.objects.get_or_create(user=instance)


        
