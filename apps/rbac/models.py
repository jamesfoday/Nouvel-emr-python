# apps/rbac/models.py
from django.conf import settings
from django.db import models

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True, default="")
    def __str__(self) -> str:
        return self.name

class RoleBinding(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_bindings"
    )
    role = models.ForeignKey(Role, on_delete=models.CASCADE, related_name="bindings")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "role"], name="uniq_user_role")
        ]

    def __str__(self) -> str:
        return f"{self.user} → {self.role}"
