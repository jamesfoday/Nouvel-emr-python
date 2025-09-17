# apps/appointments/services.py
from __future__ import annotations

from datetime import datetime, timedelta, time
from typing import List, Dict, Optional

from django.db.models import Q
from django.utils import timezone

from .models import Appointment, Availability

# only consider these as "blocking" for conflicts & free-slot calc.
ACTIVE_STATUSES = ("scheduled", "confirmed")


def _ensure_aware(dt: datetime, tz=None) -> datetime:
    """
    I normalize any datetime to be timezone-aware in the project TZ.
    """
    if dt is None:
        return dt
    if dt.tzinfo is not None:
        return dt
    tz = tz or timezone.get_current_timezone()
    return timezone.make_aware(dt, tz)


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    """
    I use the [start, end) convention; end == start is OK.
    """
    return a_start < b_end and b_start < a_end


def conflicting_appointments(
    *,
    clinician_id: int,
    patient_id: int,
    start: datetime,
    end: datetime,
    exclude_id: Optional[int] = None,
):
    """
    I return a queryset of appointments that overlap the given window for either the clinician or the patient.
    I ignore cancelled/completed and I can optionally exclude one appointment by id.
    """
    tz = timezone.get_current_timezone()
    start = _ensure_aware(start, tz)
    end = _ensure_aware(end, tz)

    q = (
        Q(status__in=ACTIVE_STATUSES)
        & (Q(clinician_id=clinician_id) | Q(patient_id=patient_id))
        & Q(start__lt=end, end__gt=start)  # overlap rule
    )

    qs = Appointment.objects.filter(q)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.select_related("patient", "clinician").order_by("start")


def get_free_slots(
    *,
    clinician_id: int,
    date_from: datetime,
    date_to: datetime,
    slot_minutes: Optional[int] = None,
    max_results: int = 100,
) -> List[Dict]:
    """
    I generate conflict-free slots for a clinician within [date_from, date_to).
    I respect weekly Availability templates and skip overlapping appointments.
    Returns items shaped for FreeSlotSerializer: {start, end, duration_minutes, clinician}.
    """
    tz = timezone.get_current_timezone()
    date_from = _ensure_aware(date_from, tz)
    date_to = _ensure_aware(date_to, tz)

    if date_from >= date_to:
        return []

    # Prefetch existing active appointments overlapping the range (skip cancelled/completed).
    appts = list(
        Appointment.objects.filter(
            clinician_id=clinician_id,
            status__in=ACTIVE_STATUSES,
            start__lt=date_to,
            end__gt=date_from,
        )
        .only("id", "start", "end", "status")
        .order_by("start")
    )

    # Pull weekly availability windows
    windows = list(
        Availability.objects.filter(clinician_id=clinician_id, is_active=True)
        .order_by("weekday", "start_time")
    )
    if not windows:
        return []

    results: List[Dict] = []

    # Iterate day by day
    cur = date_from
    while cur < date_to and len(results) < max_results:
        cur_date = cur.astimezone(tz).date()  # day in local tz
        weekday = cur_date.weekday()  # 0..6
        day_windows = [w for w in windows if w.weekday == weekday]

        for w in day_windows:
            # default slot size comes from window unless caller overrides
            sm = int(slot_minutes or w.slot_minutes)

            # Build the day's availability range in TZ
            day_start_naive = datetime.combine(cur_date, w.start_time)
            day_end_naive = datetime.combine(cur_date, w.end_time)
            day_start = _ensure_aware(day_start_naive, tz)
            day_end = _ensure_aware(day_end_naive, tz)

            # Clamp to requested overall range
            rng_start = max(day_start, date_from)
            rng_end = min(day_end, date_to)
            if rng_start >= rng_end:
                continue

            t = rng_start
            while (t + timedelta(minutes=sm)) <= rng_end and len(results) < max_results:
                s = t
                e = t + timedelta(minutes=sm)

                # Skip if overlaps any active appointment
                if not any(_overlaps(s, e, a.start, a.end) for a in appts):
                    results.append(
                        {
                            "start": s,
                            "end": e,
                            "duration_minutes": sm,
                            "clinician": clinician_id,
                        }
                    )

                # Step to next slot
                t = e

        # Move to next day at 00:00 in TZ
        next_midnight_naive = datetime.combine(cur_date + timedelta(days=1), time(0, 0))
        cur = _ensure_aware(next_midnight_naive, tz)

    return results[:max_results]
