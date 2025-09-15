
from apps.audit.models import AuditEvent


def _client_ip(request) -> str | None:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(request, action: str, object_type: str = "", object_id: str | int | None = None):
    #  centralizing audit insert so it stays consistent across the app.
    AuditEvent.objects.create(
        actor=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
        action=action,
        object_type=object_type,
        object_id=str(object_id or ""),
        ip=_client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", ""),
    )
