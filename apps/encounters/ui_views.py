# apps/encounters/ui_views.py

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q

from apps.accounts.models import User
from apps.patients.models import Patient
from .models import Encounter, VitalSign, ClinicalNote


# ---- Helpers ---------------------------------------------------------------

def _assert_can_view(request, clinician: User) -> None:
    """Only the clinician themself or a superuser can access these pages."""
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        raise PermissionDenied("You do not have access to this dashboard.")


def _get_clinician_or_403(pk: int) -> User:
    return get_object_or_404(User, pk=pk, is_staff=True)


# ---- Views ----------------------------------------------------------------

@login_required
def list_encounters(request, pk: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    # Query params
    q = (request.GET.get("q") or "").strip()
    status_param = (request.GET.get("status") or "open").lower()  # open|closed|cancelled|all

    # Base queryset
    qs = (
        Encounter.objects
        .filter(clinician=clinician)
        .select_related("patient")
    )

    # Status filter (use your TextChoices safely)
    allowed = {Encounter.Status.OPEN, Encounter.Status.CLOSED, Encounter.Status.CANCELLED}
    if status_param != "all" and status_param in allowed:
        qs = qs.filter(status=status_param)

    # Search (patient name OR reason OR location)
    if q:
        qs = qs.filter(
            Q(patient__full_name__icontains=q) |
            Q(reason__icontains=q) |
            Q(location__icontains=q)
        )

    encounters = qs.order_by("-start")[:200]

    return render(
        request,
        "clinicians/console/encounters/list.html",
        {
            "clinician": clinician,
            "encounters": encounters,
            "q": q,
            "status": status_param,
        },
    )


@login_required
def create_encounter(request, pk: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        reason = (request.POST.get("reason") or "").strip()
        location = (request.POST.get("location") or "").strip()

        if not patient_id:
            return render(
                request,
                "clinicians/console/encounters/create.html",
                {"clinician": clinician, "error": "Select a patient."},
            )

        patient = get_object_or_404(Patient, pk=patient_id)
        enc = Encounter.objects.create(
            clinician=clinician,
            patient=patient,
            reason=reason,
            location=location,
            start=timezone.now(),
        )
        # ensure vitals row exists so the form has values
        VitalSign.objects.get_or_create(encounter=enc)
        return redirect("encounters_ui:view", pk=clinician.pk, eid=enc.pk)

    return render(
        request,
        "clinicians/console/encounters/create.html",
        {"clinician": clinician},
    )


@login_required
def view_encounter(request, pk: int, eid: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    enc = get_object_or_404(
        Encounter.objects.select_related("patient"),
        pk=eid,
        clinician=clinician,
    )
    vitals, _ = VitalSign.objects.get_or_create(encounter=enc)
    notes = (
        ClinicalNote.objects
        .filter(encounter=enc)
        .select_related("author")
        .order_by("-created_at")[:100]
    )

    return render(
        request,
        "clinicians/console/encounters/view.html",
        {"clinician": clinician, "enc": enc, "vitals": vitals, "notes": notes},
    )


@login_required
@require_POST
def save_vitals(request, pk: int, eid: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)
    vitals, _ = VitalSign.objects.get_or_create(encounter=enc)

    def _num(name, cast=int):
        raw = request.POST.get(name)
        if raw is None or raw == "":
            return None
        try:
            return cast(raw)
        except Exception:
            return None

    vitals.systolic = _num("systolic", int)
    vitals.diastolic = _num("diastolic", int)
    vitals.heart_rate = _num("heart_rate", int)
    vitals.resp_rate = _num("resp_rate", int)
    vitals.temperature_c = _num("temperature_c", float)
    vitals.spo2 = _num("spo2", int)
    vitals.weight_kg = _num("weight_kg", float)
    vitals.height_cm = _num("height_cm", float)
    vitals.save()

    return render(
        request,
        "clinicians/console/encounters/_vitals.html",
        {"enc": enc, "vitals": vitals},
    )


@login_required
@require_POST
def add_note(request, pk: int, eid: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)

    kind = (request.POST.get("kind") or "N").strip()[:2]
    content = (request.POST.get("content") or "").strip()
    if content:
        ClinicalNote.objects.create(
            encounter=enc,
            author=request.user,
            kind=kind,
            content=content,
        )

    notes = (
        ClinicalNote.objects
        .filter(encounter=enc)
        .select_related("author")
        .order_by("-created_at")[:100]
    )

    return render(
        request,
        "clinicians/console/encounters/_notes.html",
        {"enc": enc, "notes": notes},
    )


@login_required
@require_POST
def delete_note(request, pk: int, eid: int, nid: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)
    note = get_object_or_404(ClinicalNote, pk=nid, encounter=enc)

    # Allow the note author, the clinician, or a superuser to delete
    if not (request.user.is_superuser or request.user == note.author or request.user == clinician):
        raise PermissionDenied("You can't delete this note.")

    note.delete()

    notes = (
        ClinicalNote.objects
        .filter(encounter=enc)
        .select_related("author")
        .order_by("-created_at")[:100]
    )

    return render(
        request,
        "clinicians/console/encounters/_notes.html",
        {"enc": enc, "notes": notes},
    )


@login_required
def close_encounter(request, pk: int, eid: int):
    clinician = _get_clinician_or_403(pk)
    _assert_can_view(request, clinician)

    enc = get_object_or_404(Encounter, pk=eid, clinician=clinician)
    if enc.status != Encounter.Status.CLOSED:
        enc.status = Encounter.Status.CLOSED
        enc.end = timezone.now()
        enc.save(update_fields=["status", "end"])

    return redirect("encounters_ui:view", pk=clinician.pk, eid=enc.pk)
