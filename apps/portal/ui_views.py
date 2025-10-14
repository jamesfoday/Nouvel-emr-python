# apps/portal/ui_views.py
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.template import loader, TemplateDoesNotExist
from django.utils import timezone

# --- guarded imports, project may toggle apps on/off in dev ---
try:
    from apps.patients.models import Patient  # runtime use
except Exception:
    Patient = None  # type: ignore[misc,assignment]

try:
    from apps.appointments.models import Appointment
except Exception:
    Appointment = None  # type: ignore

try:
    from apps.documents.models import Document
except Exception:
    Document = None  # type: ignore

from apps.messaging.models import Message

if TYPE_CHECKING:
    from apps.patients.models import Patient as PatientModel
else:
    class PatientModel:  # minimal stand-in for type hints
        pass

User = get_user_model()

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


# ============================================================================
# helpers
# ============================================================================

def _patient_from_request(request: HttpRequest) -> Optional["PatientModel"]:
    """
    Resolve the 'active patient' for the portal session.

    Works even if Patient has no FK to auth.User:
      1) Superuser impersonation (?patient_id or session key)
      2) If Patient model has 'user' FK, use it
      3) Match by email
      4) Match by first/last name
    """
    if not Patient:
        return None

    # 1) superuser impersonation
    if getattr(request.user, "is_superuser", False):
        pid = request.session.get("portal_impersonate_patient_id")
        if pid:
            p = Patient.objects.filter(pk=pid, is_active=True, merged_into__isnull=True).first()
            if p:
                return p
        qpid = request.GET.get("patient_id")
        if qpid:
            p = Patient.objects.filter(pk=qpid, is_active=True, merged_into__isnull=True).first()
            if p:
                return p

    # 2) FK 'user' if it exists
    try:
        patient_fields = {f.name for f in Patient._meta.get_fields()}
    except Exception:
        patient_fields = set()
    if "user" in patient_fields:
        p = Patient.objects.filter(
            user=request.user,
            is_active=True,
            merged_into__isnull=True,
        ).first()
        if p:
            return p

    # 3) email match
    email = (getattr(request.user, "email", "") or "").strip()
    if email:
        p = Patient.objects.filter(
            email__iexact=email,
            is_active=True,
            merged_into__isnull=True,
        ).first()
        if p:
            return p

    # 4) name match
    first = (getattr(request.user, "first_name", "") or "").strip()
    last  = (getattr(request.user, "last_name", "") or "").strip()
    if first or last:
        filters = {"is_active": True, "merged_into__isnull": True}
        if first:
            filters["given_name__iexact"] = first
        if last:
            filters["family_name__iexact"] = last
        p = Patient.objects.filter(**filters).first()
        if p:
            return p

    return None


def _clinician_user_qs():
    return User.objects.filter(is_active=True, is_staff=True)


def _is_admin_preview(request: HttpRequest) -> bool:
    return bool(request.user.is_superuser and request.session.get("portal_impersonate_patient_id"))


def _render_best(request: HttpRequest, candidate_templates: list[str], context: dict) -> HttpResponse:
    try:
        tmpl = loader.select_template(candidate_templates)
        return HttpResponse(tmpl.render(context | {"__template_used": tmpl.origin.template_name}, request))
    except TemplateDoesNotExist:
        used = ", ".join(candidate_templates)
        html = f"""
        <section class="p-4 text-sm text-gray-600">
          <div class="font-semibold">Template not found</div>
          <div>Looked for: <code>{used}</code></div>
        </section>
        """
        return HttpResponse(html)


# ============================================================================
# dashboard & impersonation
# ============================================================================

@login_required
def dashboard(request: HttpRequest):
    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        raise PermissionDenied("No patient context.")
    return _render_best(
        request,
        ["portal/dashboard.html", "portal/partials/dashboard.html"],
        {"patient": patient},
    )


@login_required
def dashboard_as(request: HttpRequest, patient_id: int):
    if not request.user.is_superuser:
        raise PermissionDenied()
    request.session["portal_impersonate_patient_id"] = patient_id
    messages.success(request, "Impersonation enabled.")
    return redirect("portal_ui:home")


@login_required
def dashboard_stop_impersonate(request: HttpRequest):
    if not request.user.is_superuser:
        raise PermissionDenied()
    request.session.pop("portal_impersonate_patient_id", None)
    messages.info(request, "Impersonation stopped.")
    return redirect("portal_ui:home")


# ============================================================================
# panels (patient dashboard)
# ============================================================================

@login_required
def appts_panel(request: HttpRequest):
    """
    Patient's 'Consultation' card.
    Now loads upcoming appointments for the active patient and passes them as `appts`.
    Safe across optional fields: start/status/meet_url/clinician may or may not exist.
    """
    appts = []
    if Appointment:
        patient = _patient_from_request(request)
        if patient:
            qs = Appointment.objects.all()

            # Filter by patient if field exists
            try:
                appt_fields = {f.name for f in Appointment._meta.get_fields()}
            except Exception:
                appt_fields = set()

            if "patient" in appt_fields:
                qs = qs.filter(patient=patient)

            # Upcoming: start >= now if 'start' exists
            now = timezone.now()
            if "start" in appt_fields:
                qs = qs.filter(start__gte=now).order_by("start")
            else:
                qs = qs.order_by("id")

            # Exclude cancelled if a status field exists
            if "status" in appt_fields:
                qs = qs.exclude(status__iexact="cancelled")

            appts = list(qs[:10])

    return _render_best(
        request,
        ["portal/appts.html", "portal/partials/appts_panel.html", "portal/appts_panel.html"],
        {"appts": appts},
    )


@login_required
def documents_panel(request: HttpRequest):
    return _render_best(
        request,
        ["portal/documents.html", "portal/partials/documents_panel.html", "portal/documents_panel.html"],
        {},
    )


@login_required
def tests_panel(request: HttpRequest):
    return _render_best(
        request,
        ["portal/tests.html", "portal/partials/tests_panel.html", "portal/tests_panel.html"],
        {},
    )


@login_required
def rx_panel(request: HttpRequest):
    return _render_best(
        request,
        ["portal/rx.html", "portal/partials/rx_panel.html", "portal/rx_panel.html"],
        {},
    )


# ============================================================================
# messaging (patient side)
# ============================================================================

@login_required
def messages_panel(request: HttpRequest):
    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        return HttpResponseBadRequest("No patient")

    clinicians = list(_clinician_user_qs()[:50])

    unread_rows = (
        Message.objects.filter(
            kind="dm",
            to_user=request.user,
            is_read=False,
            from_user__in=clinicians,
        )
        .values("from_user_id")
        .annotate(cnt=Count("id"))
    )
    unread_by_sender = {r["from_user_id"]: r["cnt"] for r in unread_rows}
    for c in clinicians:
        c.unread_count = unread_by_sender.get(c.id, 0)

    admin_preview = _is_admin_preview(request)
    return _render_best(
        request,
        ["portal/messages.html", "portal/partials/messages.html"],
        {"clinicians": clinicians, "admin_preview": admin_preview},
    )


@login_required
def messages_thread(request: HttpRequest):
    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        return HttpResponseBadRequest("No patient")

    cid = request.GET.get("clinician_id")
    if not cid:
        return HttpResponseBadRequest("Missing clinician")

    clinician = get_object_or_404(User, pk=cid, is_staff=True, is_active=True)

    msgs = (
        Message.objects.filter(kind="dm")
        .filter(
            (Q(from_user=request.user) & Q(to_user=clinician))
            | (Q(from_user=clinician) & Q(to_user=request.user))
        )
        .order_by("id")[:200]
    )

    # mark incoming as read
    Message.objects.filter(
        kind="dm",
        from_user=clinician,
        to_user=request.user,
        is_read=False,
    ).update(is_read=True)

    admin_preview = _is_admin_preview(request)
    return _render_best(
        request,
        ["portal/partials/_thread.html", "portal/_thread.html"],
        {"msgs": msgs, "clinician": clinician, "me": request.user, "admin_preview": admin_preview},
    )


@login_required
def messages_send(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    if _is_admin_preview(request):
        return HttpResponseBadRequest("Admin preview cannot send messages.")

    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        return HttpResponseBadRequest("No patient")

    cid = request.POST.get("clinician_id")
    body = (request.POST.get("body") or "").strip()
    if not cid or not body:
        return HttpResponseBadRequest("Missing fields")

    clinician = get_object_or_404(User, pk=cid, is_staff=True, is_active=True)

    m = Message.objects.create(
        kind="dm",
        from_user=request.user,
        to_user=clinician,
        subject="",
        body=body,
        is_read=False,
    )

    html_resp = _render_best(
        request,
        ["portal/partials/_msg_bubble.html", "portal/_msg_bubble.html"],
        {"m": m, "me": request.user},
    )
    html_resp["HX-Trigger"] = '{"refresh-badges": true}'
    return html_resp


@login_required
def messages_chat(request: HttpRequest):
    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        return HttpResponseBadRequest("No patient")

    cid = request.GET.get("clinician_id")
    if not cid:
        return messages_panel(request)

    clinician = get_object_or_404(User, pk=cid, is_staff=True, is_active=True)

    msgs = (
        Message.objects.filter(kind="dm")
        .filter(
            (Q(from_user=request.user) & Q(to_user=clinician))
            | (Q(from_user=clinician) & Q(to_user=request.user))
        )
        .order_by("id")[:200]
    )

    Message.objects.filter(
        kind="dm",
        from_user=clinician,
        to_user=request.user,
        is_read=False,
    ).update(is_read=True)

    admin_preview = _is_admin_preview(request)
    resp = _render_best(
        request,
        ["portal/messages_chat.html", "portal/partials/messages_chat.html"],
        {"clinician": clinician, "msgs": msgs, "me": request.user, "admin_preview": admin_preview},
    )
    resp["HX-Trigger"] = '{"refresh-badges": true}'
    return resp


# ============================================================================
# global unread badge (patient)
# ============================================================================

@login_required
def unread_total_badge(request: HttpRequest):
    total = Message.objects.filter(
        to_user=request.user,
        is_read=False,
        kind="dm"
    ).count()
    return _render_best(
        request,
        ["portal/partials/_inbox_badge.html", "portal/_inbox_badge.html"],
        {"total": total},
    )


# ============================================================================
# profile
# ============================================================================

@login_required
def profile(request: HttpRequest):
    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        raise PermissionDenied("No patient context.")
    return _render_best(
        request,
        ["portal/profile.html", "portal/partials/profile.html"],
        {"patient": patient},
    )


@login_required
def profile_update(request: HttpRequest):
    if request.method == "POST":
        messages.success(request, "Profile updated.")
        return redirect("portal_ui:profile")
    return _render_best(
        request,
        ["portal/profile_update.html", "portal/partials/profile_update.html"],
        {},
    )


@login_required
def appts_list(request: HttpRequest):
    """
    Full-page list of the patient's consultations with simple filters.
    Query params:
      - status: all|upcoming|past|cancelled (if Appointment has 'status')
      - q: search by clinician name
      - page, page_size
    """
    patient = _patient_from_request(request)
    if not patient and not request.user.is_superuser:
        raise PermissionDenied("No patient context.")

    appts = []
    total = 0
    status = (request.GET.get("status") or "all").lower()
    q = (request.GET.get("q") or "").strip()
    page = request.GET.get("page") or "1"
    page_size = request.GET.get("page_size") or "10"

    try:
        page_size_i = max(5, min(50, int(page_size)))
    except Exception:
        page_size_i = 10

    if Appointment:
        qs = Appointment.objects.all()

        # limit to this patient if FK exists
        try:
            appt_fields = {f.name for f in Appointment._meta.get_fields()}
        except Exception:
            appt_fields = set()

        if "patient" in appt_fields:
            qs = qs.filter(patient=patient)

        now = timezone.now()

        if status == "upcoming" and "start" in appt_fields:
            qs = qs.filter(start__gte=now)
        elif status == "past" and "start" in appt_fields:
            qs = qs.filter(start__lt=now)
        elif status == "cancelled" and "status" in appt_fields:
            qs = qs.filter(status__iexact="cancelled")

        # search by clinician's name/username if possible
        if q:
            # be defensive: only filter if relation exists
            if "clinician" in appt_fields:
                qs = qs.filter(
                    Q(clinician__first_name__icontains=q)
                    | Q(clinician__last_name__icontains=q)
                    | Q(clinician__username__icontains=q)
                )

        # sensible ordering
        if "start" in appt_fields:
            qs = qs.order_by("-start")
        else:
            qs = qs.order_by("-id")

        paginator = Paginator(qs, page_size_i)
        try:
            page_obj = paginator.page(page)
        except (PageNotAnInteger, EmptyPage):
            page_obj = paginator.page(1)

        appts = list(page_obj.object_list)
        total = paginator.count
    else:
        page_obj = None

    return _render_best(
        request,
        ["portal/appts_list.html"],
        {
            "appts": appts,
            "total": total,
            "status": status,
            "q": q,
            "page_obj": page_obj,
            "page_size": page_size_i,
        },
    )