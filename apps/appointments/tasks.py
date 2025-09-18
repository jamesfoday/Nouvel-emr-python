# apps/appointments/tasks.py
from __future__ import annotations

from email.utils import formatdate
from typing import Optional
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.utils import timezone

from .models import Appointment
from .ics import calendar_text_for_appointments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _render_subject_and_body(template_name: str, ctx: dict[str, str]) -> tuple[str, str]:
    """
    Render a TXT template whose first line starts with 'Subject:'.
    Everything after the first line is the email body.
    If the template is missing, fall back to a generic subject/body.
    """
    try:
        raw = render_to_string(f"emails/appointments/{template_name}.txt", ctx)
        lines = raw.splitlines()
        subject_line = lines[0].replace("Subject:", "").strip() if lines else ""
        body = "\n".join(lines[1:]).strip()
        subject = subject_line or "Appointment update"
        body = body or "Your appointment was updated."
        return subject, body
    except TemplateDoesNotExist:
        return "Appointment update", "Your appointment was updated."


def _ics_bytes_for(appt: Appointment, *, method: str) -> bytes:
    """
    Produce RFC5545 ICS bytes using our helper.
    If calendar_text_for_appointments doesn't support `method`, gracefully fall back.
    """
    try:
        ics_text = calendar_text_for_appointments([appt], method=method)  # newer helper
    except TypeError:
        ics_text = calendar_text_for_appointments([appt])  # older helper
    return ics_text.encode("utf-8")


# ---------------------------------------------------------------------------
# Outbound mail with ICS attachment
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2)
def send_appointment_email(
    self,
    appt_id: int,
    kind: str = "created",                      # 'created' | 'rescheduled' | 'cancelled' | 'reminder'
    to_override: Optional[list[str]] = None,    # allow custom recipients (tests, admin, etc.)
):
    """
    Email the patient (or `to_override`) with an ICS attachment so they can
    add/update the event in their calendar app in one tap.
    """
    # Feature flag: let ops switch notifications off without code changes.
    if not getattr(settings, "NOTIFY_APPOINTMENTS", True):
        return {"skipped": True, "reason": "notifications disabled"}

    appt = Appointment.objects.select_related("patient", "clinician").get(id=appt_id)

    # Recipients: default to patient email, unless override provided.
    to_list = to_override or ([appt.patient.email] if appt.patient.email else [])
    if not to_list:
        return {"skipped": True, "reason": "no recipient email", "appt": appt.id}

    # Localized time strings for template.
    tz = timezone.get_current_timezone()
    start_local = timezone.localtime(appt.start, tz)
    end_local = timezone.localtime(appt.end, tz)

    ctx = {
        "patient_name": f"{appt.patient.given_name} {appt.patient.family_name}".strip(),
        "clinician_name": getattr(appt.clinician, "display_name", None) or appt.clinician.get_username(),
        "start_local": start_local.strftime("%a, %d %b %Y %H:%M"),
        "end_local": end_local.strftime("%H:%M"),
        "tzname": start_local.tzname() or "UTC",
        "location": appt.location or "",
        "reason": appt.reason or "",
        "kind": kind,
        "appointment_id": appt.id,
    }

    # Template names match `kind` (created/rescheduled/cancelled/reminder).
    subject, body = _render_subject_and_body(kind, ctx)

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@nouvel.local"),
        to=to_list,
    )

    # ICS METHOD: 'REQUEST' for create/reschedule/reminder, 'CANCEL' for cancel.
    method = "REQUEST" if kind in {"created", "rescheduled", "reminder"} else "CANCEL"
    ics_bytes = _ics_bytes_for(appt, method=method)
    msg.attach(
        filename=f"appointment-{appt.id}.ics",
        content=ics_bytes,
        mimetype=f'text/calendar; charset=UTF-8; method={method}',
    )

    # Helpful headers for some clients (e.g., Outlook)
    msg.extra_headers = {
        "Date": formatdate(localtime=True),
        "X-Entity-Ref-ID": str(appt.id),
    }

    msg.send(fail_silently=False)
    return {"sent": True, "to": to_list, "kind": kind, "appt": appt.id}


# ---------------------------------------------------------------------------
# Reminder sweeper (24h & 2h)
# ---------------------------------------------------------------------------

REMINDER_WINDOW_MINUTES = 5  # run every ~5m in prod; this is the tolerance


def _due_queryset(hours_ahead: int, sent_field: str):
    """
    Find appointments whose start time is ~hours_ahead from now (± window),
    with active status, and that haven't been reminded via `sent_field`.
    """
    now = timezone.now()
    target = now + timedelta(hours=hours_ahead)
    window_start = target - timedelta(minutes=REMINDER_WINDOW_MINUTES)
    window_end = target + timedelta(minutes=REMINDER_WINDOW_MINUTES)

    return (
        Appointment.objects.select_related("patient", "clinician")
        .filter(
            status__in=["scheduled", "confirmed"],
            start__gte=window_start,
            start__lt=window_end,
        )
        .filter(**{f"{sent_field}__isnull": True})
        .order_by("start")
    )


@shared_task(bind=True, max_retries=1)
def send_due_reminders(self):
    """
    Look for appointments ~24h and ~2h from now and send reminder emails once.
    Marks `reminder_24h_sent_at` / `reminder_2h_sent_at` to prevent duplicates.
    """
    totals = {"24h": 0, "2h": 0}

    # 24h reminders
    for appt in _due_queryset(24, "reminder_24h_sent_at"):
        if not appt.patient.email:
            continue
        send_appointment_email.delay(appt.id, kind="reminder")
        appt.reminder_24h_sent_at = timezone.now()
        appt.save(update_fields=["reminder_24h_sent_at"])
        totals["24h"] += 1

    # 2h reminders
    for appt in _due_queryset(2, "reminder_2h_sent_at"):
        if not appt.patient.email:
            continue
        send_appointment_email.delay(appt.id, kind="reminder")
        appt.reminder_2h_sent_at = timezone.now()
        appt.save(update_fields=["reminder_2h_sent_at"])
        totals["2h"] += 1

    return totals
