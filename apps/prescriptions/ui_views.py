# apps/prescriptions/ui_views.py
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from .models import Prescription

def _assert_can_view(request, clinician: User):
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        raise PermissionDenied("You do not have access to this dashboard.")

@login_required
def list_prescriptions(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = request.GET.get("q", "").strip()
    qs = Prescription.objects.filter(clinician=clinician).select_related("patient")
    if q:
        qs = qs.filter(title__icontains=q) | qs.filter(patient__full_name__icontains=q)

    return render(request, "clinicians/console/prescriptions/list.html", {
        "clinician": clinician,
        "prescriptions": qs[:200],
        "q": q,
    })

@login_required
def create_prescription(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        title = request.POST.get("title", "").strip()
        body  = request.POST.get("body", "").strip()
        status = request.POST.get("status", "draft")

        if not (patient_id and title):
            return render(request, "clinicians/console/prescriptions/create.html", {
                "clinician": clinician,
                "error": "Please choose a patient and enter a title.",
            })

        patient = get_object_or_404(Patient, pk=patient_id)
        Prescription.objects.create(
            clinician=clinician, patient=patient, title=title, body=body, status=status
        )
        return redirect("prescriptions_ui:list", pk=clinician.pk)

    return render(request, "clinicians/console/prescriptions/create.html", {
        "clinician": clinician,
        "date_default": timezone.localdate().isoformat(),
    })

@login_required
def delete_prescription(request, pk, rx_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    if request.method == "POST":
        rx = get_object_or_404(Prescription, pk=rx_id, clinician=clinician)
        rx.delete()
    return redirect("prescriptions_ui:list", pk=clinician.pk)

@login_required
def view_prescription(request, pk, rx_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    rx = get_object_or_404(Prescription, pk=rx_id, clinician=clinician)
    return render(request, "clinicians/console/prescriptions/view.html", {"clinician": clinician, "rx": rx})
