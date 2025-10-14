# apps/appointments/views.py
from django.shortcuts import render, redirect
from django.http import HttpResponseBadRequest
from django.utils import timezone
from django.db.models import Q
from .models import Appointment
from apps.patients.models import Patient

def appointment_create(request):
    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        date_str   = request.POST.get("date")
        hour       = request.POST.get("hour")
        minute     = request.POST.get("minute")

        if not (patient_id and date_str and hour is not None and minute is not None):
            return HttpResponseBadRequest("Missing fields")

        patient = Patient.objects.get(id=patient_id)

        # combine date + time to naive dt in local tz (adjust if you store UTC)
        dt = timezone.datetime.fromisoformat(f"{date_str}T{int(hour):02d}:{int(minute):02d}:00")
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())

        # Simple conflict rule: another appointment for this patient at the same start
        conflict = Appointment.objects.filter(
            Q(patient=patient) & Q(start=dt)
        ).exists()
        if conflict:
            return render(request, "appointments/create.html", {
                "error": "This patient already has an appointment at that time.",
                "prefill": {"patient_id": patient_id, "date": date_str, "hour": hour, "minute": minute}
            })

        appt = Appointment.objects.create(
            patient=patient,
            start=dt,
            # add other fields (clinician, location, duration) as needed
        )
        return redirect("appointments:detail", appt.id)  # adjust to your detail route

    return render(request, "appointments/create.html")


from django.template.loader import render_to_string
from django.http import HttpResponse

def check_conflict(request):
    """HTMX endpoint: returns a tiny badge showing Available/Conflict."""
    patient_id = request.POST.get("patient_id")
    date = request.POST.get("date")
    hour = request.POST.get("hour")
    minute = request.POST.get("minute")

    status = {"state": "idle", "msg": "Pick patient + time"}
    if patient_id and date and hour is not None and minute is not None:
        dt = timezone.datetime.fromisoformat(f"{date}T{int(hour):02d}:{int(minute):02d}:00")
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        conflict = Appointment.objects.filter(patient_id=patient_id, start=dt).exists()
        status = {"state": "ok" if not conflict else "conflict",
                  "msg": "Available" if not conflict else "Conflict at selected time"}

    html = render_to_string("appointments/_availability_badge.html", {"status": status})
    return HttpResponse(html)
