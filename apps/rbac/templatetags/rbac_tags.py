# apps/rbac/templatetags/rbac_tags.py
from django import template
from django.urls import reverse, NoReverseMatch

register = template.Library()

@register.filter
def in_roles(user, roles_csv: str) -> bool:
    """
    Usage: {% if request.user|in_roles:"reception,receptionist,frontdesk" %} ... {% endif %}
    """
    if not getattr(user, "is_authenticated", False):
        return False
    want = {r.strip() for r in roles_csv.split(",") if r.strip()}
    try:
        have = set(
            user.role_bindings.select_related("role").values_list("role__name", flat=True)
        )
    except Exception:
        have = set()
    return bool(have & want)

@register.simple_tag(takes_context=True)
def absurl(context, view_name, *args, **kwargs):
    """
    Build a same-origin absolute URL using the current request.
    Usage:
      {% absurl 'patients_ui:reception_patients_list' %}
      {% absurl 'patients_ui:reception_patient_toggle_active' p.pk %}
    """
    request = context.get("request")
    path = reverse(view_name, args=args, kwargs=kwargs)
    if not request:
        return path  # fallback to path-only
    return request.build_absolute_uri(path)

# -------- Safe reverse helpers (avoid template 500s on name mismatch) --------

@register.simple_tag
def url_or(view_name, *args, default="#", **kwargs):
    """
    Return relative URL or `default` if reverse fails.
    Usage: {% url_or 'patients_ui:detail' p.pk default='#' %}
    """
    try:
        return reverse(view_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return default

@register.simple_tag(takes_context=True)
def absurl_or(context, view_name, *args, default="#", **kwargs):
    """
    Return absolute same-origin URL or `default` if reverse fails.
    Perfect for HTMX targets.
    Usage: {% absurl_or 'patients_ui:reception_patient_toggle_active' p.pk default='#' %}
    """
    request = context.get("request")
    try:
        path = reverse(view_name, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return default
    if not request:
        return path
    return request.build_absolute_uri(path)
