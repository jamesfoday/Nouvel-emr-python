from datetime import datetime
from django.db.models import Q
from .models import Appointment

ACTIVE_STATUSES = {"scheduled", "confirmed"}  # I ignore completed/cancelled in conflict checks

def conflicting_appointments(*, clinician_id: int, patient_id: int, start, end, exclude_id: int | None = None):
    q = Q(status__in=ACTIVE_STATUSES) & (
        Q(clinician_id=clinician_id) | Q(patient_id=patient_id)
    ) & Q(start__lt=end, end__gt=start)  # overlap rule

    qs = Appointment.objects.filter(q)
    if exclude_id:
        qs = qs.exclude(id=exclude_id)
    return qs.select_related("patient", "clinician").order_by("start")
