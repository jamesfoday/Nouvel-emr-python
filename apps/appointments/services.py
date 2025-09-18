# apps/appointments/services.py
from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Iterable, List, Dict, Optional

from django.db.models import Q
from django.utils import timezone

from .models import Appointment, Availability

# Only these statuses block the calendar
ACTIVE_STATUSES = {"scheduled", "confirmed"}


def _aware(dt: datetime) -> datetime:
    """Make a naive datetime aware in the current timezone."""
    if timezone.is_aware(dt):
        return dt
    return timezone.make_aware(dt, timezone.get_current_timezone())


def conflicting_appointments(
    *,
    clinician_id: int,
    patient_id: int,
    start: datetime,
    end: datetime,
    exclude_id: Optional[int] = None,
):
    """
    Return a queryset of active appointments that overlap [start,end)
    for either the clinician or the patient.
    """
    start = _aware(start)
    end = _aware(end)

    q = (
        Q(status__in=ACTIVE_STATUSES)
        & Q(start__lt=end, end__gt=start)  # overlap rule
        & (Q(clinician_id=clinician_id) | Q(patient_id=patient_id))
    )
    qs = Appointment.objects.filter(q)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.select_related("patient", "clinician").order_by("start")


# -------- Availability expansion & suggestions --------

def _date_iter(d0: date, d1: date):
    """Inclusive date iterator."""
    step = timedelta(days=1)
    d = d0
    while d <= d1:
        yield d
        d += step


def _windows_for_range(
    *,
    clinician_id: int,
    date_from: datetime,
    date_to: datetime,
):
    """
    Expand weekly availability windows into concrete [start,end) ranges
    over the given date interval. Yields (start_dt, end_dt, slot_minutes).
    """
    df = _aware(date_from)
    dt = _aware(date_to)
    tz = timezone.get_current_timezone()

    windows = list(
        Availability.objects.filter(
            clinician_id=clinician_id,
            is_active=True,
        ).only("weekday", "start_time", "end_time", "slot_minutes")
    )

    by_weekday: dict[int, list[Availability]] = {}
    for w in windows:
        by_weekday.setdefault(w.weekday, []).append(w)

    for day in _date_iter(df.date(), dt.date()):
        wd = day.weekday()  # 0..6
        day_windows = by_weekday.get(wd, [])
        if not day_windows:
            continue
        for w in day_windows:
            start_dt = timezone.make_aware(datetime.combine(day, w.start_time), tz)
            end_dt = timezone.make_aware(datetime.combine(day, w.end_time), tz)
            # clamp to requested range
            start_dt = max(start_dt, df)
            end_dt = min(end_dt, dt)
            if start_dt < end_dt:
                yield start_dt, end_dt, int(w.slot_minutes or 30)


def _has_conflict(
    *,
    clinician_id: int,
    patient_id: Optional[int],
    start: datetime,
    end: datetime,
    exclude_id: Optional[int] = None,
) -> bool:
    """True if [start,end) overlaps any active appts for clinician or patient."""
    q = Q(status__in=ACTIVE_STATUSES) & Q(start__lt=end, end__gt=start) & (
        Q(clinician_id=clinician_id) | (Q(patient_id=patient_id) if patient_id else Q())
    )
    qs = Appointment.objects.filter(q)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.exists()


def suggest_free_slots(
    *,
    clinician_id: int,
    date_from: datetime,
    date_to: datetime,
    duration_minutes: int,
    step_minutes: Optional[int] = None,
    patient_id: Optional[int] = None,
    limit: int = 50,
    exclude_appointment_id: Optional[int] = None,
) -> List[Dict]:
    """
    Generate free slots between date_from and date_to based on weekly availability,
    avoiding overlaps with existing appointments.
    """
    df = _aware(date_from)
    dt = _aware(date_to)
    duration = timedelta(minutes=int(duration_minutes))
    out: List[Dict] = []

    for win_start, win_end, default_step in _windows_for_range(
        clinician_id=clinician_id, date_from=df, date_to=dt
    ):
        step = timedelta(minutes=int(step_minutes or default_step))
        cur = win_start
        while cur + duration <= win_end:
            slot_start = cur
            slot_end = cur + duration

            if not _has_conflict(
                clinician_id=clinician_id,
                patient_id=patient_id,
                start=slot_start,
                end=slot_end,
                exclude_id=exclude_appointment_id,
            ):
                out.append(
                    {
                        "start": slot_start,
                        "end": slot_end,
                        "duration_minutes": duration_minutes,
                        "clinician": clinician_id,
                    }
                )
                if len(out) >= limit:
                    return out
            cur += step

    return out
