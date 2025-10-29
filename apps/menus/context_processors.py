# apps/menus/context_processors.py
from .models import Menu

def menus_debug(request):
    """
    Exposes all Menu rows to templates for quick debugging.
    Usage example in templates:
      {% for m in menus_debug %}{{ m.key }} (active={{ m.is_active }}){% endfor %}
    """
    try:
        return {"menus_debug": Menu.objects.all().only("key", "is_active")}
    except Exception:
        # Fail-safe: never break the page if DB is unavailable
        return {"menus_debug": []}
