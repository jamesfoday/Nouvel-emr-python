from rest_framework.permissions import BasePermission


class HasRole(BasePermission):
    # use this as a base permission; subclasses set required_roles.
    required_roles: set[str] = set()

    def has_permission(self, request, view) -> bool:
        if not self.required_roles:
            return True
        if not request.user.is_authenticated:
            return False
        roles = set(
            request.user.role_bindings.select_related("role").values_list("role__name", flat=True)
        )
        return bool(roles & self.required_roles)


def roles_required(*roles: str):
    # generate a concrete permission class per endpoint/view.
    class _P(HasRole):
        required_roles = set(roles)

    return _P
