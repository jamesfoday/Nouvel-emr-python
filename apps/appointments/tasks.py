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
    """Render 'Subject: ...' on line 1, rest is body; fallback if template missing."""
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
    """Produce RFC5545 ICS bytes using our helper."""
    try:
        ics_text = calendar_text_for_appointments([appt], method=method)
    except TypeError:
        ics_text = calendar_text_for_appointments([appt])
    return ics_text.encode("utf-8")

# ---------------------------------------------------------------------------
# Outbound mail with ICS attachment
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2)
def send_appointment_email(
    self,
    appt_id: int,
    kind: str = "created",                      # 'created' | 'rescheduled' | 'cancelled' | 'reminder'
    to_override: Optional[list[str]] = None,    # custom recipients (tests/admin)
):
    """Email the patient (or override) with an ICS attachment."""
    if not getattr(settings, "NOTIFY_APPOINTMENTS", True):
        return {"skipped": True, "reason": "notifications disabled"}

    appt = Appointment.objects.select_related("patient", "clinician").get(id=appt_id)

    to_list = to_override or ([appt.patient.email] if appt.patient.email else [])
    if not to_list:
        return {"skipped": True, "reason": "no recipient email", "appt": appt.id}

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

    subject, body = _render_subject_and_body(kind, ctx)

    msg = EmailMessage(
        subject=subject,
        body=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@nouvel.local"),
        to=to_list,
    )

    method = "REQUEST" if kind in {"created", "rescheduled", "reminder"} else "CANCEL"
    ics_bytes = _ics_bytes_for(appt, method=method)
    msg.attach(
        filename=f"appointment-{appt.id}.ics",
        content=ics_bytes,
        mimetype=f"text/calendar; charset=UTF-8; method={method}",
    )

    msg.extra_headers = {
        "Date": formatdate(localtime=True),
        "X-Entity-Ref-ID": str(appt.id),
    }

    msg.send(fail_silently=False)
    return {"sent": True, "to": to_list, "kind": kind, "appt": appt.id}

# ---------------------------------------------------------------------------
# Reminder sweeper (24h & 2h)
# ---------------------------------------------------------------------------

REMINDER_WINDOW_MINUTES = 5  # tolerance around exact 24h/2h marks

def _due_queryset(hours_ahead: int, sent_field: str):
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
            **{f"{sent_field}__isnull": True},
        )
        .order_by("start")
    )

@shared_task(bind=True, max_retries=1)
def send_due_reminders(self):
    """Send 24h & 2h reminders once, marking timestamps to avoid duplicates."""
    totals = {"24h": 0, "2h": 0}

    for appt in _due_queryset(24, "reminder_24h_sent_at"):
        if not appt.patient.email:
            continue
        send_appointment_email.delay(appt.id, kind="reminder")
        appt.reminder_24h_sent_at = timezone.now()
        appt.save(update_fields=["reminder_24h_sent_at"])
        totals["24h"] += 1

    for appt in _due_queryset(2, "reminder_2h_sent_at"):
        if not appt.patient.email:
            continue
        send_appointment_email.delay(appt.id, kind="reminder")
        appt.reminder_2h_sent_at = timezone.now()
        appt.save(update_fields=["reminder_2h_sent_at"])
        totals["2h"] += 1

    return totals
