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
from datetime import timedelta
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from apps.appointments.models import Appointment, Availability
from apps.appointments.services import suggest_free_slots
from apps.patients.models import Patient
from datetime import datetime
from apps.appointments.models import Appointment


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


from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from apps.patients.models import Patient as PatientT

def _current_patient_for_user(user) -> Optional["PatientT"]:
    """
    Best-effort way to map a portal user -> Patient.
    Adjust to your project’s relationship if needed.
    """
   
    if hasattr(user, "patient") and isinstance(getattr(user, "patient"), Patient):
        return user.patient

   
    prof = getattr(user, "profile", None)
    if prof and hasattr(prof, "patient") and isinstance(prof.patient, Patient):
        return prof.patient

    
    email = (user.email or "").strip().lower()
    if email:
        try:
            return Patient.objects.get(email__iexact=email)
        except Patient.DoesNotExist:
            pass

    return None


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


    


@login_required
@require_http_methods(["GET"])
def book_appt_page(request):
    """
    Renders the booking page with filters and a Find Slots button.
    """
    clinicians = (
        User.objects.filter(is_staff=True, is_active=True)
        .order_by("last_name", "first_name", "id")
    )

    # Defaults
    now = timezone.localtime()
    date_from = now
    date_to = now + timedelta(days=7)
    duration = 30

    clinician_id = request.GET.get("clinician")
    try:
        clinician_id = int(clinician_id) if clinician_id else None
    except ValueError:
        clinician_id = None

    ctx = {
        "clinicians": clinicians,
        "clinician_id": clinician_id,
        "date_from": date_from,
        "date_to": date_to,
        "duration": duration,
    }
    return render(request, "portal/consultations/book.html", ctx)


@login_required
@require_http_methods(["GET"])
def book_appt_slots(request):
    """
    HTMX endpoint: returns a grid of available slots for the chosen clinician & window.
    """
    clinician_id = request.GET.get("clinician_id")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    duration = int(request.GET.get("duration") or 30)

    if not clinician_id:
        return HttpResponseBadRequest("Missing clinician_id")

    # Parse ISO local datetime values from the datetime-local inputs
    def _parse_local(dt_str: str):
        # Expect e.g. "2025-10-14T09:30"
        return timezone.make_aware(timezone.datetime.fromisoformat(dt_str)) if dt_str else None

    df = _parse_local(date_from)
    dt = _parse_local(date_to)

    if not df:
        df = timezone.localtime()
    if not dt:
        dt = df + timedelta(days=7)

    # Call your availability service
    slots = suggest_free_slots(
        clinician_id=int(clinician_id),
        date_from=df,
        date_to=dt,
        duration_minutes=duration,
        step_minutes=None,
        patient_id=None,  # if you want to bias results by patient constraints, pass id here
        limit=40,
    )

    return render(
        request,
        "portal/consultations/_slots.html",
        {"slots": slots, "duration": duration},
    )


@login_required
@require_POST
def book_appt_create(request):
    """
    Creates an Appointment in 'requested' state from a selected slot.
    Redirects the patient to their consultations list.
    """
    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    clinician_id = request.POST.get("clinician_id")
    start_iso = (request.POST.get("start_iso") or "").strip()
    duration = int(request.POST.get("duration") or 30)

    if not clinician_id or not start_iso:
        return HttpResponseBadRequest("Missing fields")

    clinician = get_object_or_404(User, pk=int(clinician_id), is_staff=True, is_active=True)


    try:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        return HttpResponseBadRequest("Invalid start time")

    if dt.tzinfo is None:
        start = timezone.make_aware(dt)
    else:
        start = dt.astimezone(timezone.get_current_timezone())

    
    model_fields = {f.name for f in Appointment._meta.get_fields()
                    if getattr(f, "concrete", False) and not getattr(f, "many_to_many", False)}

    appt_kwargs = {
        "clinician": clinician,
        "patient": patient,
        "start": start,
    }

    if "duration_minutes" in model_fields:
        appt_kwargs["duration_minutes"] = duration
    elif "duration" in model_fields:
        appt_kwargs["duration"] = duration
    elif "end" in model_fields:
        appt_kwargs["end"] = start + timedelta(minutes=duration)
  

    appt = Appointment(**appt_kwargs)

    if "status" in model_fields:
        appt.status = "requested"

    appt.save()

    try:
        from apps.appointments.tasks import send_appointment_email
        send_appointment_email.delay(appt.id, "requested")
    except Exception:
        pass

    try:
        return redirect("portal_ui:appts_list")
    except Exception:
        return redirect("portal_ui:home")
