from django import template
register = template.Library()

@register.filter
def in_roles(user, roles_csv: str) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    want = {r.strip() for r in roles_csv.split(",") if r.strip()}
    have = set(user.role_bindings.select_related("role").values_list("role__name", flat=True))
    return bool(have & want)
