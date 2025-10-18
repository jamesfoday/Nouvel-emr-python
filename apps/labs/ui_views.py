# apps/labs/ui_views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpRequest
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.db.models import Q, Prefetch, Case, When, Value, IntegerField
from django.db.models.deletion import ProtectedError

from apps.accounts.models import User
# If you don't use Patient directly in this file, you can remove this import.
# from apps.patients.models import Patient

from .models import (
    LabCatalog,
    LabOrder,
    DiagnosticReport,
    Observation,
    ExternalLabResult,
)
from .forms import LabOrderForm, DiagnosticReportForm, LabCatalogForm


# ---------------------------------------------------------------------------
# Permissions helper
# ---------------------------------------------------------------------------
def _assert_can_view(request, clinician: User):
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("No access.")


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
@login_required
def order_create(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        form = LabOrderForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.clinician = clinician
            order.save()
            messages.success(request, "Lab order created.")
            return redirect("labs_ui:lab_index", pk=clinician.pk)
    else:
        form = LabOrderForm()

    return render(request, "labs/order_form.html", {"form": form, "clinician": clinician})


# ---------------------------------------------------------------------------
# Diagnostic Report (manual entry)
# ---------------------------------------------------------------------------
@login_required
def result_create(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        form = DiagnosticReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            # If your DiagnosticReport has a clinician FK, set it here:
            # report.clinician = clinician
            report.save()
            messages.success(request, "Diagnostic report saved.")
            return redirect("labs_ui:lab_index", pk=clinician.pk)
    else:
        form = DiagnosticReportForm()

    return render(request, "labs/result_form.html", {"form": form, "clinician": clinician})


# ---------------------------------------------------------------------------
# Lab index (console home)
# ---------------------------------------------------------------------------
@login_required
def lab_index(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    orders = (
        LabOrder.objects
        .filter(clinician=clinician)
        .select_related("patient", "catalog")
        .order_by("-ordered_at")[:20]
    )

    # If you track clinician on DiagnosticReport, filter by clinician instead.
    reports = (
        DiagnosticReport.objects
        .filter(patient__isnull=False)
        .select_related("patient")
        .order_by("-issued_at")[:20]
    )

    catalogs = LabCatalog.objects.order_by("name")[:50]

    return render(
        request,
        "labs/index.html",
        {"clinician": clinician, "orders": orders, "reports": reports, "catalogs": catalogs},
    )


# ---------------------------------------------------------------------------
# Catalog CRUD
# ---------------------------------------------------------------------------
@login_required
def catalog_list(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()
    catalogs = LabCatalog.objects.all().order_by("name")
    if q:
        catalogs = catalogs.filter(
            Q(name__icontains=q) | Q(code__icontains=q) | Q(loinc_code__icontains=q)
        )

    return render(request, "labs/catalog_list.html", {"clinician": clinician, "catalogs": catalogs, "q": q})


@login_required
def catalog_create(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        form = LabCatalogForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Catalog entry created.")
            return redirect("labs_ui:catalog_list", pk=clinician.pk)
    else:
        form = LabCatalogForm()

    return render(request, "labs/catalog_form.html", {"clinician": clinician, "form": form})


@login_required
def catalog_edit(request: HttpRequest, pk: int, catalog_id: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    obj = get_object_or_404(LabCatalog, pk=catalog_id)
    if request.method == "POST":
        form = LabCatalogForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Catalog updated.")
            return redirect("labs_ui:catalog_list", pk=clinician.pk)
    else:
        form = LabCatalogForm(instance=obj)

    return render(request, "labs/catalog_form.html", {"clinician": clinician, "form": form})


@login_required
@require_POST
def catalog_delete(request: HttpRequest, pk: int, catalog_id: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    obj = get_object_or_404(LabCatalog, pk=catalog_id)
    try:
        obj.delete()
        messages.success(request, "Catalog deleted.")
    except ProtectedError:
        messages.error(
            request,
            "This catalog cannot be deleted because there are lab orders linked to it.",
        )
    return redirect("labs_ui:catalog_list", pk=clinician.pk)


# ---------------------------------------------------------------------------
# External Results (patient-uploaded) — INBOX + REVIEW/DECISION
# ---------------------------------------------------------------------------
@login_required
def external_results_inbox(request: HttpRequest, pk: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()
    base_qs = ExternalLabResult.objects.filter(clinician_to=clinician)

    if q:
        base_qs = base_qs.filter(
            Q(patient__given_name__icontains=q)
            | Q(patient__family_name__icontains=q)
            | Q(title__icontains=q)
            | Q(vendor_name__icontains=q)
        )

    qs = (
        base_qs
        .annotate(
            status_rank=Case(
                When(status=ExternalLabResult.Status.SUBMITTED,    then=Value(0)),
                When(status=ExternalLabResult.Status.UNDER_REVIEW, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("status_rank", "-created_at")
        .select_related("patient", "order", "clinician_to")
    )

    return render(request, "labs/external/inbox.html", {"clinician": clinician, "items": qs, "q": q})


@login_required
def external_result_review(request: HttpRequest, pk: int, result_id: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    er = get_object_or_404(ExternalLabResult, pk=result_id, clinician_to=clinician)
    if er.status == er.Status.SUBMITTED:
        er.status = er.Status.UNDER_REVIEW
        er.reviewer = request.user
        er.save(update_fields=["status", "reviewer"])

    return render(request, "labs/external/review_modal.html", {"clinician": clinician, "er": er})


@login_required
def external_result_decision(request: HttpRequest, pk: int, result_id: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    er = get_object_or_404(ExternalLabResult, pk=result_id, clinician_to=clinician)
    action = request.POST.get("action")

    if action == "accept":
        er.status = er.Status.ACCEPTED
        er.reviewed_at = timezone.now()
        er.reviewer = request.user
        er.save(update_fields=["status", "reviewed_at", "reviewer"])

        # Optionally create a DiagnosticReport so the patient sees it in Reports.
        DiagnosticReport.objects.create(
            patient=er.patient,
            performing_lab=er.vendor_name or "External",
            issued_at=er.performed_at or timezone.now(),
            status="final",
            pdf=er.file,  # reuses the file
        )
        messages.success(request, "External result accepted and added to reports.")

    elif action == "reject":
        er.status = er.Status.REJECTED
        er.reviewed_at = timezone.now()
        er.reviewer = request.user
        er.save(update_fields=["status", "reviewed_at", "reviewer"])
        messages.info(request, "External result rejected.")

    return redirect("labs_ui:external_results_inbox", pk=clinician.pk)



@login_required
def external_results_panel(request, pk: int):
    """
    Small panel for clinician dashboard:
    shows clinician's most recent external results with status priority.
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()

    base_qs = ExternalLabResult.objects.filter(clinician_to=clinician)

    if q:
        base_qs = base_qs.filter(
            Q(title__icontains=q)
            | Q(vendor_name__icontains=q)
            | Q(patient__given_name__icontains=q)
            | Q(patient__family_name__icontains=q)
        )

    items = (
        base_qs
        .annotate(
            status_rank=Case(
                When(status=ExternalLabResult.Status.UNDER_REVIEW, then=Value(0)),
                When(status=ExternalLabResult.Status.SUBMITTED,   then=Value(1)),
                When(status=ExternalLabResult.Status.ACCEPTED,    then=Value(2)),
                When(status=ExternalLabResult.Status.REJECTED,    then=Value(3)),
                default=Value(4),
                output_field=IntegerField(),
            )
        )
        .select_related("patient", "order")
        .order_by("status_rank", "-created_at")[:5]
    )

    return render(
        request,
        "labs/external/panel.html",
        {"clinician": clinician, "items": items, "q": q},
    )
