from datetime import datetime, time, timedelta

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.http import HttpResponseBadRequest

from apps.accounts.models import User
from apps.patients.models import Patient
from .services import suggest_free_slots
from .serializers import AppointmentCreateSerializer


def _clinician_qs():
    # Show only users bound to role 'clinician'; fallback to staff if no bindings exist.
    qs = User.objects.filter(role_bindings__role__name="clinician").distinct()
    if not qs.exists():
        qs = User.objects.filter(is_staff=True)
    return qs.order_by("username")


@login_required
@require_GET
def book_dialog(request):
    """
    Renders the booking modal for a given patient_id.
    """
    patient_id = request.GET.get("patient_id")
    if not patient_id:
        return HttpResponseBadRequest("Missing patient_id")
    patient = get_object_or_404(Patient, pk=patient_id)

    clinicians = _clinician_qs()
    today_str = timezone.localdate().isoformat()

    return render(
        request,
        "appointments/_book_modal.html",
        {
            "patient": patient,
            "clinicians": clinicians,
            "date_default": today_str,
        },
    )


@login_required
@require_GET
def slots_for_day(request):
    """
    Returns a button list of free slots for a clinician on a given date.
    HTMX-fragment only.
    """
    clinician_id = request.GET.get("clinician_id")
    date_str = request.GET.get("date")
    dur = int(request.GET.get("duration", "30"))

    if not clinician_id or not date_str:
        return HttpResponseBadRequest("Missing clinician_id or date")

    # Build a timezone-aware range [start_of_day, end_of_day)
    # using the server's current timezone (settings.TIME_ZONE).
    tz = timezone.get_current_timezone()
    try:
        d = datetime.fromisoformat(date_str).date()
    except ValueError:
        return HttpResponseBadRequest("Invalid date")

    start_dt = timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
    end_dt = start_dt + timedelta(days=1)

    slots = suggest_free_slots(
        clinician_id=int(clinician_id),
        start=start_dt,
        end=end_dt,
        slot_minutes=dur,
        min_gap_minutes=0,   # tweak if you want buffer between slots
        limit=30,
    )

    # Represent slots as (start_iso, end_iso, label)
    rendered_slots = []
    for s in slots:
        st = s["start"]
        en = s["end"]
        # Nicely formatted label in local time
        st_local = timezone.localtime(st, tz).strftime("%H:%M")
        en_local = timezone.localtime(en, tz).strftime("%H:%M")
        rendered_slots.append(
            {
                "start_iso": st.isoformat(),
                "end_iso": en.isoformat(),
                "label": f"{st_local} - {en_local}",
            }
        )

    return render(
        request,
        "appointments/_slot_buttons.html",
        {"slots": rendered_slots},
    )


@login_required
@require_POST
def create_from_slot(request):
    """
    Creates an appointment from a picked slot.
    Returns a tiny success fragment for the modal.
    """
    patient_id = request.POST.get("patient_id")
    clinician_id = request.POST.get("clinician_id")
    start_iso = request.POST.get("start")
    end_iso = request.POST.get("end")
    reason = request.POST.get("reason", "")
    location = request.POST.get("location", "")
    status = request.POST.get("status")  # optional

    if not all([patient_id, clinician_id, start_iso, end_iso]):
        return HttpResponseBadRequest("Missing fields")

    # Use DRF serializer for validation & saving.
    payload = {
        "patient": patient_id,
        "clinician": clinician_id,
        "start": start_iso,
        "end": end_iso,
        "reason": reason,
        "location": location,
    }
    if status:
        payload["status"] = status

    ser = AppointmentCreateSerializer(data=payload)
    ser.is_valid(raise_exception=True)
    appt = ser.save()

    # (Your API layer already logs & sends email/ICS.)
    return render(
        request,
        "appointments/_created.html",
        {"appointment": appt},
    )


