# config/settings.py
"""
Shim so DJANGO_SETTINGS_MODULE='config.settings' works.
Prefer dev in local; fall back to base if dev isn't present.
"""
try:
    from .dev import *  # noqa
except Exception:
    from .base import *  # noqa
