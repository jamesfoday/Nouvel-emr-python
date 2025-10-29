# apps/rbac/templatetags/absurl.py
from django import template
from django.urls import reverse

register = template.Library()

@register.simple_tag(takes_context=True)
def absurl(context, view_name, *args, **kwargs):
    """
    Build a same-origin absolute URL from a view name, based on the current request.
    Example: {% absurl 'patients_ui:reception_patients_list' %}
    """
    request = context.get("request")
    path = reverse(view_name, args=args, kwargs=kwargs)
    if not request:
        return path  # fallback to path-only
    return request.build_absolute_uri(path)
