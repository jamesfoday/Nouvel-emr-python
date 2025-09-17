from __future__ import annotations
from datetime import datetime, timezone as py_tz

#  escape text per RFC 5545 rules (commas, semicolons, backslashes, newlines).
def _ics_escape(value: str) -> str:
    if value is None:
        return ""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
        .replace("\r", "")
    )

def _fmt(dt: datetime) -> str:
    # export everything as UTC (Z) to avoid TZ headaches in clients.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=py_tz.utc)
    dt = dt.astimezone(py_tz.utc)
    return dt.strftime("%Y%m%dT%H%M%SZ")

def event_lines_for_appointment(appt) -> list[str]:
    uid = f"appointment-{appt.id}@nouvel-emr"
    summary = f"Appointment: {appt.patient} with {getattr(appt.clinician, 'username', appt.clinician_id)}"
    description_parts = []
    if appt.reason:
        description_parts.append(f"Reason: {appt.reason}")
    description_parts.append(f"Status: {appt.status}")
    description = "\\n".join(_ics_escape(p) for p in description_parts)
    location = _ics_escape(appt.location or "")

    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_fmt(appt.created_at or appt.start)}",
        f"DTSTART:{_fmt(appt.start)}",
        f"DTEND:{_fmt(appt.end)}",
        f"SUMMARY:{_ics_escape(summary)}",
        f"DESCRIPTION:{description}",
        f"LOCATION:{location}",
        "END:VEVENT",
    ]
    return lines

def calendar_text_for_appointments(appts) -> str:
    # I wrap one or more VEVENTs into a VCALENDAR.
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Nouvel EMR//Appointments//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for a in appts:
        lines.extend(event_lines_for_appointment(a))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
