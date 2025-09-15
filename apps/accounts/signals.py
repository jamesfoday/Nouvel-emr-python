from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.dispatch import receiver
from apps.audit.utils import log_event


@receiver(user_logged_in)
def audit_login(sender, request, user, **kwargs):
    #  record successful interactive logins.
    log_event(request, "auth.login", "User", user.id)


@receiver(user_logged_out)
def audit_logout(sender, request, user, **kwargs):
    #  record explicit logouts.
    log_event(request, "auth.logout", "User", getattr(user, "id", ""))


@receiver(user_login_failed)
def audit_login_failed(sender, credentials, request, **kwargs):
    #  record failed logins without attaching a user id.
    username = (credentials or {}).get("username", "")
    log_event(request, "auth.login_failed", "Auth", username)
