# apps/appointments/ui_views.py
from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist
from django.urls import reverse

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.audit.utils import log_event

from .serializers import AppointmentCreateSerializer
from .services import suggest_free_slots, conflicting_appointments
from .tasks import send_appointment_email


def _clinician_qs():
    """
    Prefer users bound to role 'clinician'; fall back to staff if none.
    """
    qs = User.objects.filter(role_bindings__role__name="clinician").distinct()
    if not qs.exists():
        qs = User.objects.filter(is_staff=True)
    return qs.order_by("username")


@login_required
@require_GET
def appointments_home(request):
    """
    Console landing page for appointments (HTMX-friendly).
    """
    return render(request, "appointments/console/home.html", {})


def _active_clinician(request):
    """Figure out which clinician this page is for."""
    pk = request.GET.get("clinician")
    if pk:
        c = get_object_or_404(User, pk=pk, is_staff=True)
        if request.user.is_superuser or request.user.pk == c.pk:
            return c

    # 2) the logged-in staff user
    if getattr(request.user, "is_staff", False):
        return request.user

    # 3) fallback
    qs = _clinician_qs()
    return qs.first()


@login_required
@require_GET
def new_appointment_page(request):
    clinician = _active_clinician(request)
    clinicians = _clinician_qs()
    ctx = {
        "clinician": clinician,
        "clinicians": clinicians,
        "date_default": timezone.localdate().isoformat(),
        "durations": [15, 20, 30, 45, 60],
    }
    return render(request, "appointments/console/create.html", ctx)


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

    ctx = {
        "patient": patient,
        "clinicians": clinicians,
        "date_default": today_str,
        "durations": [15, 20, 30, 45, 60],
    }
    return render(request, "appointments/_book_modal.html", ctx)


@login_required
@require_GET
def slots_for_day(request):
    """
    Returns a button list of free slots for a clinician on a given date.
    HTMX fragment only.
    Query params: clinician_id, date (YYYY-MM-DD), duration (minutes), patient_id (forwarded)
    """
    clinician_id = request.GET.get("clinician_id")
    date_str = request.GET.get("date")
    duration = int(request.GET.get("duration", "30"))
    patient_id = request.GET.get("patient_id")

    if not clinician_id or not date_str:
        return HttpResponseBadRequest("Missing clinician_id or date")

    try:
        day = datetime.fromisoformat(date_str).date()
    except ValueError:
        return HttpResponseBadRequest("Invalid date (use YYYY-MM-DD)")

    slots = suggest_free_slots(
        clinician_id=int(clinician_id),
        day=day,
        duration_minutes=duration,
        max_results=30,
    )

    tz = timezone.get_current_timezone()
    rendered_slots = []
    for s in slots:
        st = s["start"]
        en = s["end"]
        if timezone.is_naive(st):
            st = timezone.make_aware(st)
        if timezone.is_naive(en):
            en = timezone.make_aware(en)
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
        "appointments/_free_slots.html",
        {
            "slots": rendered_slots,
            "patient_id": patient_id,
            "clinician_id": clinician_id,
            "duration": duration,
            "date": date_str,
        },
    )


@login_required
@require_POST
def create_from_slot(request):
    """
    Creates an appointment from a picked slot (HTMX POST).
    Fields: patient_id, clinician_id, start, end, [reason], [location], [status]
    """
    patient_id = request.POST.get("patient_id")
    clinician_id = request.POST.get("clinician_id")
    start_iso = request.POST.get("start")
    end_iso = request.POST.get("end")
    reason = (request.POST.get("reason") or "").strip()
    location = (request.POST.get("location") or "").strip()
    status = request.POST.get("status")  # optional

    if not all([patient_id, clinician_id, start_iso, end_iso]):
        return HttpResponseBadRequest("Missing fields")

    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
    except ValueError:
        return HttpResponseBadRequest("start/end must be ISO 8601")

    if timezone.is_naive(start):
        start = timezone.make_aware(start)
    if timezone.is_naive(end):
        end = timezone.make_aware(end)

    # NEW: allow override when user clicks "Create anyway" in conflict panel
    ignore = request.POST.get("ignore_conflicts") == "1"

    conflicts = list(
        conflicting_appointments(
            clinician_id=int(clinician_id),
            patient_id=int(patient_id),
            start=start,
            end=end,
        )
    )
    if conflicts and not ignore:
        return render(
            request,
            "appointments/_conflict.html",
            {"conflicts": conflicts[:10]},
            status=409,
        )

    payload = {
        "patient": patient_id,
        "clinician": clinician_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "reason": reason,
        "location": location,
    }
    if status:
        payload["status"] = status

    ser = AppointmentCreateSerializer(data=payload)
    ser.is_valid(raise_exception=True)
    appt = ser.save()

    # Audit + email/ICS
    log_event(request, "appt.create.ui", "Appointment", appt.id)
    try:
        send_appointment_email.delay(appt.id, "created")
    except Exception:
        pass

    # Redirect to clinician consultation list
    redirect_url = reverse("clinicians_ui:consultations_all", args=[int(clinician_id)])
    if request.headers.get("HX-Request"):
        return HttpResponse(status=204, headers={"HX-Redirect": redirect_url})
    return redirect(redirect_url)
