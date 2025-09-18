# apps/appointments/email.py
from __future__ import annotations

from typing import Literal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.formats import date_format

from .models import Appointment
from .ics import calendar_text_for_appointments

Kind = Literal["created", "rescheduled", "cancelled"]


def _subject_for(kind: Kind) -> str:
    # keep subjects short & scannable.
    return {
        "created": "Your appointment is scheduled",
        "rescheduled": "Your appointment was rescheduled",
        "cancelled": "Your appointment was cancelled",
    }[kind]


def _context_for(kind: Kind, appt: Appointment) -> dict:
    # compute user-friendly, localized times for the email.
    tz = timezone.get_current_timezone()
    start_local = timezone.localtime(appt.start, tz)
    end_local = timezone.localtime(appt.end, tz)
    return {
        "kind": kind,
        "patient": appt.patient,
        "clinician": appt.clinician,
        "start": start_local,
        "end": end_local,
        "start_date": date_format(start_local, "DATE_FORMAT"),
        "start_time": date_format(start_local, "TIME_FORMAT"),
        "end_time": date_format(end_local, "TIME_FORMAT"),
        "location": appt.location,
        "reason": appt.reason,
        "appointment_id": appt.id,
    }


def _render_bodies(context: dict) -> tuple[str, str | None]:
    """
    I render text & (optionally) HTML bodies.
    If HTML template is missing, I fall back to text-only.
    """
    body_text = render_to_string("email/appointments/body.txt", context)
    body_html = None
    try:
        body_html = render_to_string("email/appointments/body.html", context)
    except Exception:
        # HTML template is optional; text-only is fine.
        pass
    return body_text, body_html


def _ics_bytes_for(appt: Appointment, *, method: str = "REQUEST") -> bytes:
    """
    I build a standards-compliant ICS using our existing multi-event helper.
    For cancellation, I still provide a VCALENDAR so clients can update/delete.
    """
    ics_text = calendar_text_for_appointments([appt], method=method)
    return ics_text.encode("utf-8")


def send_appt_email(kind: Kind, appt: Appointment) -> str:
    """
    I send an appointment email with an ICS attachment.
    Returns "sent"|"skipped".
    """
    if not getattr(settings, "NOTIFY_APPOINTMENTS", True):
        return "skipped"

    recipients: list[str] = []
    if appt.patient.email:
        recipients.append(appt.patient.email)
    if getattr(appt.clinician, "email", None):
        recipients.append(appt.clinician.email)

    if not recipients:
        return "skipped"

    subject = _subject_for(kind)
    context = _context_for(kind, appt)
    body_text, body_html = _render_bodies(context)

    message = EmailMultiAlternatives(
        subject=subject,
        body=body_text,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@nouvel.local"),
        to=recipients,
    )
    if body_html:
        message.attach_alternative(body_html, "text/html")

    # ICS METHOD: REQUEST for create/reschedule, CANCEL for cancel.
    method = "REQUEST" if kind in {"created", "rescheduled"} else "CANCEL"
    message.attach(
        filename=f"appointment-{appt.id}.ics",
        content=_ics_bytes_for(appt, method=method),
        mimetype='text/calendar; charset="utf-8"; method=%s' % method,
    )

    message.send(fail_silently=False)
    return "sent"
