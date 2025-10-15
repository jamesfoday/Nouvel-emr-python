# apps/portal/ui_views.py
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, FileResponse, Http404
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
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders
import io
from os.path import basename
import mimetypes






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


try:
    from apps.prescriptions.models import Prescription
except Exception:
   
    Prescription = None

User = get_user_model()

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

try:
    from apps.documents.models import Document
except Exception:
    Document = None 





from typing import Optional, TYPE_CHECKING
if TYPE_CHECKING:
    from apps.patients.models import Patient as PatientT

def _current_patient_for_user(user) -> Optional["PatientT"]:
   
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


def _current_patient_for_user(user):
    """Return the Patient linked to this user (portal account)."""
    try:
        from apps.patients.models import Patient
    except Exception:
        return None
    return getattr(user, "patient", None) or Patient.objects.filter(email__iexact=user.email).first()

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

    # Only clinicians this patient is allowed to contact
    clinicians_qs = _allowed_clinicians_for(patient) if patient else User.objects.none()
    clinicians = list(clinicians_qs.order_by("last_name", "first_name", "id")[:50])

    # Unread counts from allowed clinicians only
    unread_rows = (
        Message.objects.filter(
            kind="dm",
            to_user=request.user,
            is_read=False,
            from_user__in=clinicians_qs,
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

    # Enforce: patient can only DM allowed clinicians
    allowed_ids = set(_allowed_clinicians_for(patient).values_list("id", flat=True)) if patient else set()
    if clinician.id not in allowed_ids and not request.user.is_superuser:
        return HttpResponseForbidden("Not allowed.")

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

    # Enforce: patient can only DM allowed clinicians
    allowed_ids = set(_allowed_clinicians_for(patient).values_list("id", flat=True)) if patient else set()
    if clinician.id not in allowed_ids and not request.user.is_superuser:
        return HttpResponseForbidden("Not allowed.")

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

    # Enforce: patient can only DM allowed clinicians
    allowed_ids = set(_allowed_clinicians_for(patient).values_list("id", flat=True)) if patient else set()
    if clinician.id not in allowed_ids and not request.user.is_superuser:
        return HttpResponseForbidden("Not allowed.")

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
    patient = _patient_from_request(request)
    allowed_qs = _allowed_clinicians_for(patient) if patient else User.objects.none()
    total = Message.objects.filter(
        to_user=request.user,
        is_read=False,
        kind="dm",
        from_user__in=allowed_qs,
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
    from datetime import datetime
    from django.utils import timezone

    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    clinician_id = request.POST.get("clinician_id")
    start_iso = (request.POST.get("start_iso") or "").strip()
    duration = int(request.POST.get("duration") or 30)
    if not clinician_id or not start_iso:
        return HttpResponseBadRequest("Missing fields")

    # Enforce clinician restriction
    allowed_ids = set(_allowed_clinicians_for(patient).values_list("id", flat=True))
    try:
        requested_id = int(clinician_id)
    except ValueError:
        return HttpResponseForbidden("Not allowed.")
    if requested_id not in allowed_ids:
        return HttpResponseForbidden("Not allowed.")

    clinician = get_object_or_404(User, pk=requested_id, is_staff=True, is_active=True)

    # robust ISO parsing (aware/naive/'Z')
    try:
        dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        return HttpResponseBadRequest("Invalid start time")
    start = dt if dt.tzinfo else timezone.make_aware(dt)
    start = start.astimezone(timezone.get_current_timezone())

   



@login_required
@require_http_methods(["GET"])
def book_appt_calendar(request):
    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    # Only allowed clinicians for this patient
    clinicians = _allowed_clinicians_for(patient).order_by("last_name", "first_name", "id")

    clinician_id = request.GET.get("clinician")
    duration = int(request.GET.get("duration") or 30)

    # If there is exactly ONE allowed clinician, preselect it
    only_id = None
    if clinicians.count() == 1:
        only_id = clinicians.first().id
        clinician_id = clinician_id or str(only_id)

    # week start handling 
    from datetime import datetime, timedelta
    from django.utils import timezone
    today_local = timezone.localdate()
    week_start_str = request.GET.get("week_start")
    try:
        start_date = datetime.fromisoformat(week_start_str).date() if week_start_str else today_local
    except Exception:
        start_date = today_local
    days = [start_date + timedelta(days=i) for i in range(7)]

    ctx = {
        "clinicians": clinicians,
        "clinician_id": int(clinician_id) if clinician_id else None,
        "duration": duration,
        "week_start": start_date,
        "days": days,
        "only_id": only_id,  # to help the template hide the select
    }
    return render(request, "portal/consultations/book_calendar.html", ctx)



@login_required
@require_http_methods(["GET"])
def book_appt_slots_grid(request):
    from datetime import datetime, timedelta
    from django.utils import timezone

    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    clinician_id = (request.GET.get("clinician_id") or "").strip()
    duration = int(request.GET.get("duration") or 30)

    # Week start (local date), default to today if missing/invalid
    week_start_str = request.GET.get("week_start")
    try:
        week_start_date = datetime.fromisoformat(week_start_str).date() if week_start_str else timezone.localdate()
    except Exception:
        week_start_date = timezone.localdate()

    days = [week_start_date + timedelta(days=i) for i in range(7)]
    hours = list(range(0, 24))

    # Missing clinician -> friendly empty state
    if not clinician_id:
        return render(
            request,
            "portal/consultations/_calendar_grid.html",
            {
                "days": days,
                "hours": hours,
                "slots_by_day": {},
                "duration": duration,
                "clinician_id": None,
                "notice": "Please select a clinician to load availability.",
            },
        )

    # Enforce clinician restriction
    allowed_ids = set(_allowed_clinicians_for(patient).values_list("id", flat=True))
    try:
        requested_id = int(clinician_id)
    except ValueError:
        return HttpResponseForbidden("Not allowed.")

    if requested_id not in allowed_ids:
        # Show empty grid with a clear message (no hard 403 page for HTMX)
        return render(
            request,
            "portal/consultations/_calendar_grid.html",
            {
                "days": days,
                "hours": hours,
                "slots_by_day": {},
                "duration": duration,
                "clinician_id": None,
                "notice": "You’re not allowed to book with this clinician.",
            },
        )

    # Build week window and fetch slots
    tz = timezone.get_current_timezone()
    date_from = timezone.make_aware(datetime.combine(days[0], datetime.min.time()), tz)
    date_to = timezone.make_aware(datetime.combine(days[-1] + timedelta(days=1), datetime.min.time()), tz)

    try:
        slots = suggest_free_slots(
            clinician_id=requested_id,
            date_from=date_from,
            date_to=date_to,
            duration_minutes=duration,
            step_minutes=None,
            patient_id=None,
            limit=500,
        )
    except Exception:
        return render(
            request,
            "portal/consultations/_calendar_grid.html",
            {
                "days": days,
                "hours": hours,
                "slots_by_day": {},
                "duration": duration,
                "clinician_id": requested_id,
                "notice": "Couldn’t load availability. Please try again.",
            },
        )

    # Group + sort
    slots_by_day = {}
    for s in slots:
        sdt = s["start"] if isinstance(s, dict) else getattr(s, "start", None)
        if not sdt:
            continue
        sdt = sdt.astimezone(tz)
        d = sdt.date()
        slots_by_day.setdefault(d, []).append(sdt)
    for d, arr in slots_by_day.items():
        arr.sort()

    return render(
        request,
        "portal/consultations/_calendar_grid.html",
        {
            "days": days,
            "hours": hours,
            "slots_by_day": slots_by_day,
            "duration": duration,
            "clinician_id": requested_id,
        },
    )



def _allowed_clinicians_for(patient):
    """
    Return a queryset of clinicians the patient is allowed to book with.
    Priority:
      1) patient.primary_clinician (if present)
      2) patient.clinician (if present)
      3) patient.created_by (if staff)
      4) last clinician from existing appointments (fallback)
    """
    
    direct_users = []
    for attr in ("primary_clinician", "clinician", "created_by"):
        if hasattr(patient, attr):
            u = getattr(patient, attr)
            if u and getattr(u, "is_staff", False):
                direct_users.append(u)

    if direct_users:
        ids = {u.id for u in direct_users if getattr(u, "is_active", True)}
        return User.objects.filter(id__in=ids, is_staff=True, is_active=True)

    
    try:
        from apps.appointments.models import Appointment
        last = (
            Appointment.objects
            .filter(patient=patient)
            .exclude(clinician__isnull=True)
            .order_by("-start")
            .first()
        )
        if last and last.clinician and last.clinician.is_staff and last.clinician.is_active:
            return User.objects.filter(id=last.clinician_id, is_staff=True, is_active=True)
    except Exception:
        pass

    
    return User.objects.none()


@login_required
def portal_rx_list(request):
    """
    Patient-facing list of their prescriptions, newest first.
    """
    if Prescription is None:
        return HttpResponseBadRequest("Prescriptions module not installed.")

    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    q = (request.GET.get("q") or "").strip()

    qs = Prescription.objects.filter(patient=patient).order_by("-created_at", "-id")
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(body__icontains=q))

    return render(
        request,
        "portal/prescriptions/list.html",
        {
            "prescriptions": list(qs[:200]),
            "q": q,
            "today": timezone.localdate(),
        },
    )


@login_required
def portal_rx_detail(request, rx_id: int):
    if Prescription is None:
        return HttpResponseBadRequest("Prescriptions module not installed.")

    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    rx = get_object_or_404(Prescription, pk=rx_id, patient=patient)

    content = getattr(rx, "body", None)
    if content is None:
        content = getattr(rx, "text", "")

    template = "portal/prescriptions/detail.html"
    if request.GET.get("as") == "modal":
        template = "portal/prescriptions/_detail_modal.html"

    return render(
        request,
        template,
        {"rx": rx, "content": content},
    )




@login_required
def portal_rx_download(request, rx_id: int):
    if Prescription is None:
        return HttpResponseBadRequest("Prescriptions module not installed.")

    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    rx = get_object_or_404(Prescription, pk=rx_id, patient=patient)

    title = getattr(rx, "title", "") or f"Prescription {rx.id}"
    body  = getattr(rx, "body", None)
    if body is None:
        body = getattr(rx, "text", "")  # soft fallback

    clinician = getattr(rx, "clinician", None)
    clinician_name = (
        getattr(clinician, "get_full_name", lambda: "")()
        or getattr(clinician, "username", "")
        or "Clinician"
    )
    created = getattr(rx, "created_at", None) or timezone.now()
    filename = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or f"prescription-{rx.id}"

    # ---------- 1) Prefer ReportLab (pure Python, no native deps) ----------
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=A4,
            leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36
        )

        styles = getSampleStyleSheet()
        H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=6)
        Meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#475569"))
        Body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=11.5, leading=16)
        Box  = ParagraphStyle("Box",  parent=styles["Normal"], backColor=colors.HexColor("#f8fafc"),
                              borderColor=colors.HexColor("#e5e7eb"), borderWidth=1, borderPadding=8,
                              fontSize=11.5, leading=16)
        Pill = ParagraphStyle("Pill", parent=styles["Normal"], textColor=colors.white,
                              backColor=colors.HexColor("#059669"), fontName="Helvetica-Bold",
                              fontSize=9, leading=12, alignment=1)

        story = []

        # Header with logo + title
        logo_path = finders.find("img/logo.png")
        row = []
        if logo_path:
            row.append(Image(logo_path, width=28, height=28))
        else:
            row.append(Paragraph("<b>N</b>", H1))
        row.append(Paragraph("Nouvel — Prescription", H1))
        header = Table([row], colWidths=[32, 450])
        header.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE")]))
        story.append(header)

        story.append(Paragraph(f"Generated {created.strftime('%Y-%m-%d %H:%M')}", Meta))
        story.append(Spacer(1, 6))

        pill_tbl = Table([[Paragraph("Prescription", Pill)]])
        pill_tbl.setStyle(TableStyle([
            ("LEFTPADDING", (0,0), (-1,-1), 8),
            ("RIGHTPADDING", (0,0), (-1,-1), 8),
            ("TOPPADDING", (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#059669")),
            ("TEXTCOLOR", (0,0), (-1,-1), colors.white),
        ]))
        story.append(pill_tbl)
        story.append(Spacer(1, 10))

        details = [
            [Paragraph("<b>Patient:</b> " + (getattr(patient, "get_full_name", lambda: "")() or str(patient)), Body),
             Paragraph("<b>Clinician:</b> " + clinician_name, Body)],
            [Paragraph("<b>Title:</b> " + title, Body),
             Paragraph("<b>Date:</b> " + created.strftime("%a, %b %d %Y · %H:%M"), Body)],
        ]
        grid = Table(details, colWidths=["*","*"])
        grid.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "TOP")]))
        story.append(grid)
        story.append(Spacer(1, 12))

        story.append(Paragraph("<b>Instructions / Medications</b>", Body))
        story.append(Spacer(1, 4))
        story.append(Paragraph((body or "").replace("\n", "<br/>"), Box))

        story.append(Spacer(1, 18))
        story.append(Paragraph(f"© {created.strftime('%Y')} Nouvel — This document was generated electronically.", Meta))

        doc.build(story)
        pdf = buffer.getvalue()
        buffer.close()

        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return resp
    except Exception:
        pass  # If ReportLab not installed, try WeasyPrint next

    # ---------- 2) Try WeasyPrint (if it works on your machine) ----------
    try:
        from weasyprint import HTML, CSS
        html = render_to_string(
            "portal/prescriptions/pdf.html",
            {
                "rx": rx,
                "title": title,
                "body": body,
                "clinician_name": clinician_name,
                "created": created,
                "patient": patient,
                "absolute_base": request.build_absolute_uri("/"),
                "logo_url": request.build_absolute_uri(staticfiles_storage.url("img/logo.png")),
            },
        )
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf(
            stylesheets=[CSS(string="@page { size: A4; margin: 22mm 18mm; } * { -weasy-hyphens: auto; }")]
        )
        resp = HttpResponse(pdf, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return resp
    except Exception:
        pass  # If WeasyPrint fails, fall back to plain text last

    # ---------- 3) Final fallback: plain text (should rarely happen now) ----------
    lines = [
        f"Title: {title}",
        f"Clinician: {clinician_name}",
        f"Date: {created.strftime('%Y-%m-%d %H:%M')}",
        "", "Prescription:", body or "", "",
    ]
    content = "\n".join(lines).strip() + "\n"
    resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}.txt"'
    return resp


def _portal_current_patient(user):
    """Use your existing helper if present; else a best-effort mapping."""
    try:
        # Prefer the project’s helper if it exists
        return _current_patient_for_user(user)  # type: ignore
    except Exception:
        pass

    # Fallbacks
    try:
        if hasattr(user, "patient"):
            return user.patient
    except Exception:
        pass
    # Try by email
    try:
        from apps.patients.models import Patient
        email = (user.email or "").strip().lower()
        if email:
            return Patient.objects.filter(email__iexact=email).first()
    except Exception:
        pass
    return None


@login_required
def docs_list(request):
    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    qs = Document.objects.filter(patient=patient).order_by("-created_at")

    docs = []
    for d in qs[:200]:
        # Compute a display name and size that templates can read
        storage_name = getattr(getattr(d, "file", None), "name", "") or ""
        display_name = basename(storage_name) if storage_name else (getattr(d, "title", "") or "Document")
        d.display_name = display_name
        d.filesize = getattr(getattr(d, "file", None), "size", None)
        docs.append(d)

    return render(
        request,
        "portal/documents/list.html",
        {"patient": patient, "docs": docs},
    )


@login_required
def doc_detail(request, doc_id: int):
    """Patient portal: document detail (inline preview if possible + download button)."""
    if Document is None:
        return HttpResponseBadRequest("Documents module not installed.")

    patient = _portal_current_patient(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    doc = get_object_or_404(Document, pk=doc_id, patient=patient)
    return render(
        request,
        "portal/documents/detail.html",
        {"patient": patient, "doc": doc},
    )


@login_required
def doc_download(request, doc_id: int):
    """Stream the original file to the patient (download)."""
    if Document is None:
        return HttpResponseBadRequest("Documents module not installed.")

    patient = _portal_current_patient(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    doc = get_object_or_404(Document, pk=doc_id, patient=patient)
    f = getattr(doc, "file", None)
    if not f:
        return HttpResponseBadRequest("File not available.")

    # Friendly filename
    base = getattr(doc, "filename", "") or getattr(doc, "title", "") or f"document-{doc.id}"
    safe = "".join(c for c in base if c.isalnum() or c in (" ", "-", "_")).strip() or f"document-{doc.id}"
    return FileResponse(f.open("rb"), as_attachment=True, filename=safe)


@login_required
def docs_download(request, doc_id: int):
    if Document is None:
        return HttpResponseBadRequest("Documents module not installed.")

    # Ensure the file belongs to the current patient
    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    doc = get_object_or_404(Document, pk=doc_id, patient=patient)

    f = getattr(doc, "file", None)
    if not f or not getattr(f, "name", ""):
        raise Http404("File missing.")

    # Pick a human filename
    title = (getattr(doc, "title", "") or "").strip()
    storage_name = f.name
    fallback = basename(storage_name) if storage_name else "document"
    nice = title or fallback
    safe = "".join(c for c in nice if c.isalnum() or c in (" ", "-", "_")).strip() or "document"
    filename = f"{safe}"

    # Guess content type
    ctype, _ = mimetypes.guess_type(storage_name)
    ctype = ctype or "application/octet-stream"

    # Use the underlying file; storage ensures streaming
    fileobj = f.open("rb")
    resp = FileResponse(fileobj, content_type=ctype, as_attachment=True, filename=filename)
    return resp


@login_required
def docs_view_modal(request, doc_id: int):
    """
    HTMX modal that previews a patient's document.
    """
    patient = _current_patient_for_user(request.user)
    if not patient:
        return HttpResponseBadRequest("No patient profile linked to your account.")

    if Document is None:
        return HttpResponseBadRequest("Documents module not installed.")

    doc = get_object_or_404(Document, pk=doc_id, patient=patient)

    # Build file info
    file_url = doc.file.url if getattr(doc, "file", None) else ""
    title = getattr(doc, "title", None) or getattr(doc, "display_name", None) \
            or (getattr(doc, "file", None) and doc.file.name) or "Document"

    name = (getattr(doc, "file", None) and doc.file.name.lower()) or ""
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    is_pdf = ext == "pdf"
    is_image = ext in {"png", "jpg", "jpeg", "gif", "webp", "bmp"}

    ctx = {
        "title": title,
        "file_url": file_url,
        "is_pdf": is_pdf,
        "is_image": is_image,
        "download_url": reverse("portal_ui:docs_download", args=[doc.id]),
    }
    return render(request, "portal/documents/_modal.html", ctx)