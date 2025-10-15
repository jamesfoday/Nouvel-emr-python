# apps/documents/ui_views.py
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponseBadRequest
from django.utils import timezone
from .models import Document 
from django.template import loader
from django.views.decorators.http import require_http_methods, require_POST
from apps.accounts.models import User
from apps.patients.models import Patient
from django.http import HttpResponseBadRequest, HttpResponse

try:
    from apps.documents.models import Document  # your existing model
except Exception:
    # Minimal fallback model if you don't have one yet
    from django.db import models
    class Document(models.Model):
        clinician = models.ForeignKey(User, on_delete=models.CASCADE, related_name="documents")
        patient   = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="documents")
        title     = models.CharField(max_length=200)
        file      = models.FileField(upload_to="documents/")
        created_at = models.DateTimeField(auto_now_add=True)
        class Meta: ordering = ["-created_at"]

def _assert_can_view(request, clinician: User):
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        raise PermissionDenied("You do not have access to this dashboard.")

@login_required
def list_documents(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    q = request.GET.get("q", "").strip()
    qs = Document.objects.filter(clinician=clinician).select_related("patient").order_by("-created_at")
    if q:
        qs = qs.filter(title__icontains=q) | qs.filter(patient__full_name__icontains=q)
    return render(request, "clinicians/console/documents/list.html", {
        "clinician": clinician,
        "docs": qs[:200],
        "q": q,
    })

@login_required
def upload_document(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        patient_id = request.POST.get("patient_id")
        title = request.POST.get("title", "").strip()
        f = request.FILES.get("file")
        if not (patient_id and title and f):
            return render(request, "clinicians/console/documents/upload.html", {
                "clinician": clinician,
                "error": "Please choose a patient, add a title, and attach a file.",
            })

        # lightweight safety
        allowed = {"application/pdf", "image/png", "image/jpeg", "image/jpg"}
        if f.content_type not in allowed or f.size > 10 * 1024 * 1024:
            return render(request, "clinicians/console/documents/upload.html", {
                "clinician": clinician,
                "error": "Only PDF/PNG/JPG up to 10MB are allowed.",
            })

        patient = get_object_or_404(Patient, pk=patient_id)
        Document.objects.create(clinician=clinician, patient=patient, title=title, file=f)
        return redirect("documents_ui:list", pk=clinician.pk)

    return render(request, "clinicians/console/documents/upload.html", {"clinician": clinician})

@login_required
def delete_document(request, pk, doc_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")
    doc = get_object_or_404(Document, pk=doc_id, clinician=clinician)
    doc.delete()
    return redirect("documents_ui:list", pk=clinician.pk)

@login_required
def view_document(request, pk, doc_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    doc = get_object_or_404(Document, pk=doc_id, clinician=clinician)
    return render(request, "clinicians/console/documents/view.html", {"clinician": clinician, "doc": doc})


@login_required
@require_http_methods(["GET"])
def doc_view_modal(request, pk, doc_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    d = get_object_or_404(Document, pk=doc_id, clinician=clinician)

    html = loader.render_to_string(
        "clinicians/console/documents/_modal_view.html",
        {"doc": d, "clinician": clinician},
        request,
    )
    return HttpResponse(html)

@login_required
@require_http_methods(["GET"])
def doc_edit_modal(request, pk, doc_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    d = get_object_or_404(Document, pk=doc_id, clinician=clinician)

    html = loader.render_to_string(
        "clinicians/console/documents/_modal_edit.html",
        {"doc": d, "clinician": clinician},
        request,
    )
    return HttpResponse(html)

@login_required
@require_POST
def doc_update(request, pk, doc_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    d = get_object_or_404(Document, pk=doc_id, clinician=clinician)

    # Minimal editable fields (adjust to your model)
    title = request.POST.get("title", "").strip()
    notes = request.POST.get("notes", "").strip()

    changed = False
    if hasattr(d, "title"):
        d.title = title
        changed = True
    if hasattr(d, "notes"):
        d.notes = notes
        changed = True
    if changed:
        d.updated_at = timezone.now() if hasattr(d, "updated_at") else d.updated_at
        d.save()

    # Return the updated view modal so the user sees changes immediately
    html = loader.render_to_string(
        "clinicians/console/documents/_modal_view.html",
        {"doc": d, "clinician": clinician},
        request,
    )
    return HttpResponse(html)
