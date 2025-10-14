from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseBadRequest
from django.utils import timezone
from django.urls import reverse

from apps.accounts.models import User
from apps.patients.models import Patient
from .models import Encounter, VitalSign, ClinicalNote

def _assert_can_view(request, clinician: User):
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        raise PermissionDenied("You do not have access to this dashboard.")

@login_required
def list_encounters(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "open")  # open|closed|all
    qs = Encounter.objects.filter(clinician=clinician).select_related("patient")

    if status != "all":
        qs = qs.filter(status=status)
    if q:
        qs = qs.filter(patient__full_name__icontains=q) | qs.filter(reason__icontains=q)

    return render(request, "clinicians/console/encounters/list.html", {
        "clinician": clinician,
        "encounters": qs.order_by("-start")[:200],
        "q": q,
        "status": status,
    })

@login_required
def create_encounter(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        reason     = request.POST.get("reason", "").strip()
        location   = request.POST.get("location", "").strip()

        if not patient_id:
            return render(request, "clinicians/console/encounters/create.html",
                          {"clinician": clinician, "error": "Select a patient."})

        patient = get_object_or_404(Patient, pk=patient_id)
        enc = Encounter.objects.create(
            clinician=clinician, patient=patient, reason=reason, location=location, start=timezone.now()
        )
        # ensure vitals object exists for the form
        VitalSign.objects.get_or_create(encounter=enc)
        return redirect("encounters_ui:view", pk=clinician.pk, eid=enc.pk)

    return render(request, "clinicians/console/encounters/create.html", {"clinician": clinician})

@login_required
def view_encounter(request, pk, eid):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    enc = get_object_or_404(Encounter.objects.select_related("patient"), pk=eid, clinician=clinician)
    vitals, _ = VitalSign.objects.get_or_create(encounter=enc)
    notes = enc.notes.select_related("author").all()[:100]
    return render(request, "clinicians/console/encounters/view.html", {
        "clinician": clinician, "enc": enc, "vitals": vitals, "notes": notes
    })

@login_required
def save_vitals(request, pk, eid):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)
    vitals, _ = VitalSign.objects.get_or_create(encounter=enc)

    def _get(name, cast=int):
        val = request.POST.get(name) or None
        try:
            return cast(val) if val is not None and val != "" else None
        except Exception:
            return None

    vitals.systolic    = _get("systolic")
    vitals.diastolic   = _get("diastolic")
    vitals.heart_rate  = _get("heart_rate")
    vitals.resp_rate   = _get("resp_rate")
    vitals.temperature_c = _get("temperature_c", cast=float)
    vitals.spo2        = _get("spo2")
    vitals.weight_kg   = _get("weight_kg", cast=float)
    vitals.height_cm   = _get("height_cm", cast=float)
    vitals.save()

    # return the updated vitals card
    return render(request, "clinicians/console/encounters/_vitals.html", {"enc": enc, "vitals": vitals})

@login_required
def add_note(request, pk, eid):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)

    kind = request.POST.get("kind", "N")
    content = (request.POST.get("content") or "").strip()
    if content:
        ClinicalNote.objects.create(encounter=enc, author=request.user, kind=kind, content=content)

    notes = enc.notes.select_related("author").all()[:100]
    return render(request, "clinicians/console/encounters/_notes.html", {"enc": enc, "notes": notes})

@login_required
def close_encounter(request, pk, eid):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)
    if enc.status != Encounter.Status.CLOSED:
        enc.status = Encounter.Status.CLOSED
        enc.end = timezone.now()
        enc.save(update_fields=["status", "end"])
    return redirect("encounters_ui:view", pk=clinician.pk, eid=enc.pk)
