from __future__ import annotations
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpRequest
from apps.accounts.models import User
from apps.patients.models import Patient
from .models import LabCatalog, LabOrder, DiagnosticReport, Observation
from django.utils import timezone

def _assert_can_view(request, clinician: User):
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("No access.")

# --- Create Order -----------------------------------------------------------
@login_required
def order_create(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    catalogs = LabCatalog.objects.order_by("name")[:200]

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        catalog_id = request.POST.get("catalog_id")
        priority   = (request.POST.get("priority") or "routine").strip()
        reason     = (request.POST.get("reason") or "").strip()
        notes      = (request.POST.get("notes") or "").strip()

        if not patient_id or not catalog_id:
            messages.error(request, "Select patient and test.")
            return render(request, "labs/order_create.html", {"clinician": clinician, "catalogs": catalogs})

        patient = get_object_or_404(Patient, pk=patient_id)
        catalog = get_object_or_404(LabCatalog, pk=catalog_id)

        LabOrder.objects.create(
            patient=patient, clinician=clinician, catalog=catalog,
            priority=priority, reason=reason, notes=notes, status="ordered",
        )
        messages.success(request, "Lab order created.")
        return redirect("clinicians_ui:tests_index", pk=clinician.pk)

    return render(request, "labs/order_create.html", {"clinician": clinician, "catalogs": catalogs})

# --- Record Result (manual) -------------------------------------------------
@login_required
def result_create(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        patient_id     = request.POST.get("patient_id")
        performing_lab = (request.POST.get("performing_lab") or "").strip()
        status         = (request.POST.get("status") or "final").strip()
        pdf            = request.FILES.get("pdf")

        if not patient_id:
            messages.error(request, "Select patient.")
            return render(request, "labs/result_create.html", {"clinician": clinician})

        patient = get_object_or_404(Patient, pk=patient_id)

        report = DiagnosticReport.objects.create(
            order=None, patient=patient, status=status,
            performing_lab=performing_lab, pdf=pdf, issued_at=timezone.now()
        )

        # parse observation rows
        names  = request.POST.getlist("obs_name[]")
        codes  = request.POST.getlist("obs_code[]")
        vals   = request.POST.getlist("obs_value[]")
        units  = request.POST.getlist("obs_unit[]")
        lows   = request.POST.getlist("obs_low[]")
        highs  = request.POST.getlist("obs_high[]")
        flags  = request.POST.getlist("obs_flag[]")
        notes  = request.POST.getlist("obs_note[]")

        for i, name in enumerate(names):
            name = (name or "").strip()
            if not name:
                continue
            val_raw = (vals[i] if i < len(vals) else "").strip()
            try:
                value_num = float(val_raw) if val_raw else None
                value_text = "" if value_num is not None else val_raw
            except ValueError:
                value_num, value_text = None, val_raw
            Observation.objects.create(
                report=report,
                name=name,
                code=(codes[i] if i < len(codes) else "").strip(),
                value_num=value_num,
                value_text=value_text,
                unit=(units[i] if i < len(units) else "").strip(),
                ref_low=(float(lows[i]) if i < len(lows) and lows[i] else None),
                ref_high=(float(highs[i]) if i < len(highs) and highs[i] else None),
                flag=(flags[i] if i < len(flags) else "").strip(),
                note=(notes[i] if i < len(notes) else "").strip(),
            )

        messages.success(request, "Result recorded.")
        return redirect("clinicians_ui:tests_index", pk=clinician.pk)

    return render(request, "labs/result_create.html", {"clinician": clinician})
