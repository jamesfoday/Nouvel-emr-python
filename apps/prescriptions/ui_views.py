# apps/prescriptions/ui_views.py
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
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
    """
    List prescriptions for a clinician.
    Uses templates/clinicians/prescriptions/list.html
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()

    qs = (
        Prescription.objects
        .filter(clinician=clinician)
        .select_related("patient")
        .order_by("-created_at")
    )

    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(patient__family_name__icontains=q)
            | Q(patient__given_name__icontains=q)
            | Q(patient__email__icontains=q)
        )

    return render(
        request,
        "clinicians/prescriptions/list.html",
        {
            "clinician": clinician,
            "prescriptions": qs[:200],
            "q": q,
        },
    )


@login_required
def create_prescription(request, pk):
    """
    Create a prescription for a clinician.
    Uses templates/clinicians/prescriptions/create.html
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        patient_id = (request.POST.get("patient_id") or "").strip()
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()
        status = (request.POST.get("status") or "draft").strip() or "draft"

        if not (patient_id and title):
            return render(
                request,
                "clinicians/prescriptions/create.html",
                {
                    "clinician": clinician,
                    "error": "Please choose a patient and enter a title.",
                    "title": title,
                    "body": body,
                    "status": status,
                    "patient_id": patient_id,
                },
            )

        patient = get_object_or_404(Patient, pk=patient_id)

        Prescription.objects.create(
            clinician=clinician,
            patient=patient,
            title=title,
            body=body,
            status=status,
        )

        return redirect("prescriptions_ui:list", pk=clinician.pk)

    return render(
        request,
        "clinicians/prescriptions/create.html",
        {
            "clinician": clinician,
            "date_default": timezone.localdate().isoformat(),
        },
    )


@login_required
def delete_prescription(request, pk, rx_id):
    """
    Delete a prescription then go back to the list.
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        rx = get_object_or_404(Prescription, pk=rx_id, clinician=clinician)
        rx.delete()

    return redirect("prescriptions_ui:list", pk=clinician.pk)


@login_required
def view_prescription(request, pk, rx_id):
    """
    View a single prescription.
    Uses templates/clinicians/prescriptions/view.html
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    rx = get_object_or_404(Prescription, pk=rx_id, clinician=clinician)

    return render(
        request,
        "clinicians/prescriptions/view.html",
        {
            "clinician": clinician,
            "rx": rx,
        },
    )
