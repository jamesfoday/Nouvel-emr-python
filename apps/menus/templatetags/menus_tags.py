# apps/menus/templatetags/menus_tags.py
from django import template
from ..models import Menu

register = template.Library()


# ---------- desktop renderer ----------

@register.inclusion_tag("menus/_menu.html", takes_context=True)
def render_menu(context, key, css_class=""):
    """
    Render a single menu (top bar) for desktops.
    Shows only top-level, visible items.
    """
    request = context.get("request")
    try:
        menu = (
            Menu.objects.prefetch_related("items__children")
            .get(key=key, is_active=True)
        )
    except Menu.DoesNotExist:
        return {"menu_items": [], "request": request, "css_class": css_class}

    items = [
        i for i in menu.items.all()
        if i.parent_id is None and i.is_active and _safe_visible(i, request.user)
    ]
    try:
        items.sort(key=lambda x: (getattr(x, "order", 0), x.pk))
    except Exception:
        pass

    return {"menu_items": items, "request": request, "css_class": css_class}


@register.simple_tag(takes_context=True)
def menu_href(context, item):
    """Resolve href for a menu item for the current request."""
    request = context.get("request")
    return item.resolved_href(request)


@register.filter
def can_see(item, user):
    """Usage: {% if item|can_see:request.user %}...{% endif %}"""
    return _safe_visible(item, user)


def _safe_visible(item, user):
    try:
        return bool(item.is_visible_for(user))
    except Exception:
        return False


# ---------- helpers for mobile/off-canvas ----------

@register.simple_tag(takes_context=True)
def menu_keys(context):
    """
    Return a list of keys of all ACTIVE menus (ordered by id).
    Usage: {% menu_keys as MENU_KEYS %}
    """
    return list(
        Menu.objects.filter(is_active=True)
        .order_by("id")
        .values_list("key", flat=True)
    )


@register.simple_tag(takes_context=True)
def default_menu_key(context):
    """
    Return a single 'best' active menu key (first by id), or '' if none.
    This supports templates that expect exactly one menu to render.
    Usage: {% default_menu_key as MENU_KEY %}
    """
    key = (
        Menu.objects.filter(is_active=True)
        .order_by("id")
        .values_list("key", flat=True)
        .first()
    )
    return key or ""


@register.simple_tag(takes_context=True)
def menu_items_for(context, key):
    """
    Return ordered top-level, visible items for a given menu key.
    Usage:
        {% menu_items_for 'main' as TOPS %}
        {% for item in TOPS %}...{% endfor %}
    """
    request = context.get("request")
    try:
        menu = (
            Menu.objects.prefetch_related("items__children")
            .get(key=key, is_active=True)
        )
    except Menu.DoesNotExist:
        return []

    items = [
        i for i in menu.items.all()
        if i.parent_id is None and i.is_active and _safe_visible(i, request.user)
    ]
    try:
        items.sort(key=lambda x: (getattr(x, "order", 0), x.pk))
    except Exception:
        pass
    return items
