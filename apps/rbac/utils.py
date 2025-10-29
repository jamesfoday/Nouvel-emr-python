# apps/rbac/utils.py
from typing import Iterable, Set
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect

# Reuse your RBAC normalizer so role name matching is consistent
from apps.rbac.permissions import _norm


def user_roles(user) -> Set[str]:
    """
    Return a normalized set of role names bound to the user.
    Mirrors the logic used in DRF permission class HasRole.
    """
    if not getattr(user, "is_authenticated", False):
        return set()

    try:
        # Assuming a reverse relation: user.role_bindings -> RoleBinding
        qs = user.role_bindings.select_related("role").values_list("role__name", flat=True)
        return {_norm(r) for r in qs}
    except Exception:
        return set()


def has_role(user, *roles: Iterable[str], allow_superuser: bool = True) -> bool:
    """
    Plain-Django helper: does the user have ANY of the given roles?
    Example usage:
        if has_role(request.user, "reception", "receptionist", "frontdesk"):
            ...
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if allow_superuser and getattr(user, "is_superuser", False):
        return True

    required = {_norm(r) for r in roles if isinstance(r, str) and r.strip()}
    if not required:
        
        return True

    roles_set = user_roles(user)

  
    if "admin" in roles_set:
        return True

    return bool(roles_set & required)


def require_roles(*roles: Iterable[str], allow_superuser: bool = True, redirect_to: str = "home"):
    """
    Decorator for plain Django views.
    Example:
        @login_required
        @require_roles("reception", "receptionist", "frontdesk")
        def my_view(request): ...
    """
    def deco(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if not (getattr(user, "is_authenticated", False) and has_role(user, *roles, allow_superuser=allow_superuser)):
                messages.error(request, "You do not have permission to perform this action.")
                return redirect(redirect_to)
            return view_func(request, *args, **kwargs)
        return _wrapped
    return deco
