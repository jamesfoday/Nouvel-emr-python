from django.apps import AppConfig

class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"     # full dotted path (app lives under apps/)
    label = "accounts"         #  keep the short label stable (AUTH_USER_MODEL uses this)

    def ready(self):
        # import signal handlers so auth events are audited on app load.
        from . import signals  # noqa: F401
