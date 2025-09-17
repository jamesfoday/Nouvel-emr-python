# apps/rbac/permissions.py
from typing import Iterable, Set

from rest_framework.permissions import BasePermission


def _norm(s: str) -> str:
    """I normalize role names for reliable comparisons."""
    return (s or "").strip().lower()


class HasRole(BasePermission):
    """
    I gate an endpoint by role names. Subclasses (or the roles_required()
    factory below) set `required_roles`.

    Behavior:
    - Superusers always pass (configurable via allow_superuser).
    - If the user has the 'admin' role, they pass everything.
    - Role matching is case-insensitive.
    """

    message = "You do not have permission to perform this action."
    required_roles: Set[str] = set()
    admin_role: str = "admin"
    allow_superuser: bool = True

    def _user_roles(self, user) -> Set[str]:
        if not getattr(user, "is_authenticated", False):
            return set()
        try:
            qs = user.role_bindings.select_related("role").values_list("role__name", flat=True)
            return {_norm(r) for r in qs}
        except Exception:
            # If the relation isn't present yet, I fail closed.
            return set()

    def has_permission(self, request, view) -> bool:
        # No roles configured → allow (useful for composing with other perms).
        if not self.required_roles:
            return True

        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        if self.allow_superuser and getattr(user, "is_superuser", False):
            return True

        roles = self._user_roles(user)
        if self.admin_role in roles:
            return True

        return bool(roles & self.required_roles)

    def has_object_permission(self, request, view, obj) -> bool:
        # For now I mirror collection permission; refine per-object later.
        return self.has_permission(request, view)


def roles_required(*roles: Iterable[str]):
    """
    I return a concrete DRF permission class that requires ANY of the given roles.

    Usage:
        permission_classes = [IsAuthenticated, roles_required("clinician", "staff", "admin")]
    """
    required = {_norm(r) for r in roles if isinstance(r, str) and r.strip()}

    class RolesRequired(HasRole):
        required_roles = required

    return RolesRequired
