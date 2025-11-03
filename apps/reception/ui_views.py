# apps/reception/ui_views.py
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Q, Count
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.forms import ReceptionistProfileForm
from apps.accounts.models import ReceptionistProfile
from apps.appointments.models import Appointment
from apps.audit.utils import log_event

# Availability/serializer pipeline (same as console/portal)
from apps.appointments.services import suggest_free_slots, conflicting_appointments
from apps.appointments.serializers import AppointmentCreateSerializer
from apps.appointments.tasks import send_appointment_email

from apps.patients.models import Patient
from apps.inquiry.models import Inquiry


User = get_user_model()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_SLOT_MINUTES = 30


def is_reception(user):
    """Reception access gate."""
    return bool(user and user.is_authenticated and user.is_staff)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clinician_qs():
    """
    Clinicians visible to reception: role 'clinician' OR is_staff.
    (Union ensures ids passed in the URL appear in the select.)
    """
    return (
        User.objects.filter(Q(role_bindings__role__name="clinician") | Q(is_staff=True))
        .distinct()
        .order_by("first_name", "last_name", "username")
    )


# ---------------- Patients (support with/without Patient.user) --------------

def _patient_has_user_fk() -> bool:
    try:
        return any(f.name == "user" for f in Patient._meta.get_fields())
    except Exception:
        return False

_HAS_USER = _patient_has_user_fk()

def _patient_fields() -> set[str]:
    try:
        return {f.name for f in Patient._meta.get_fields()}
    except Exception:
        return set()

def _model_has_field(model, name: str) -> bool:
    try:
        return any(f.name == name for f in model._meta.get_fields())
    except Exception:
        return False

def patient_queryset():
    qs = Patient.objects.all()
    return qs.select_related("user") if _HAS_USER else qs

def _full_name_from_fields(p: Patient) -> str:
    if _HAS_USER and getattr(p, "user_id", None):
        u = p.user
        name = (u.get_full_name() or "").strip()
        if name:
            return name
        if getattr(u, "username", ""):
            return u.username
        if getattr(u, "email", ""):
            return u.email
    # standalone Patient fields
    parts = [
        getattr(p, "given_name", "") or getattr(p, "first_name", "") or "",
        getattr(p, "family_name", "") or getattr(p, "last_name", "") or "",
    ]
    name = " ".join(x for x in parts if x).strip()
    if name:
        return name
    if getattr(p, "email", ""):
        return p.email
    return f"Patient #{p.pk}"

def patient_label(p: Patient):
    return _full_name_from_fields(p)

def patient_id(p: Patient):
    return p.pk  # IMPORTANT: Patient.id (not User.id)

def patient_search(qs, q: str):
    if _HAS_USER:
        return qs.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)  |
            Q(user__username__icontains=q)   |
            Q(user__email__icontains=q)
        ).order_by("user__first_name", "user__last_name", "pk")

    # Standalone Patient (no user FK) — build filters only for fields that exist
    fields = _patient_fields()
    cond = Q()
    if "given_name" in fields:   cond |= Q(given_name__icontains=q)
    if "family_name" in fields:  cond |= Q(family_name__icontains=q)
    if "first_name" in fields:   cond |= Q(first_name__icontains=q)
    if "last_name" in fields:    cond |= Q(last_name__icontains=q)
    if "email" in fields:        cond |= Q(email__icontains=q)
    if "external_id" in fields:  cond |= Q(external_id__icontains=q)

    filtered = qs.filter(cond) if cond else qs

    # Safe ordering list based on present fields
    order = []
    for f in ("given_name", "family_name", "first_name", "last_name", "email"):
        if f in fields:
            order.append(f)
    order.append("pk")
    return filtered.order_by(*order)

def patient_order(qs):
    if _HAS_USER:
        return qs.order_by("user__first_name", "user__last_name", "pk")

    fields = _patient_fields()
    order = []
    for f in ("given_name", "family_name", "first_name", "last_name", "email"):
        if f in fields:
            order.append(f)
    order.append("pk")
    return qs.order_by(*order)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_int(val, default=None):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _clinician_email(clinician):
    """Safely resolve clinician email whether clinician is a User or profile.user."""
    email = getattr(clinician, "email", None)
    if email:
        return email
    user_obj = getattr(clinician, "user", None)
    return getattr(user_obj, "email", None)


# ---------------------------------------------------------------------------
# Receptionist Dashboard & Profile
# ---------------------------------------------------------------------------

@login_required
def receptionist_dashboard(request):
    # Ensure profile exists
    profile, _ = ReceptionistProfile.objects.get_or_create(user=request.user)

    # Next 48h appointments (exclude cancelled/completed)
    now = timezone.now()
    soon = now + timedelta(hours=48)
    next48 = (
        Appointment.objects
        .select_related("clinician", "patient")
        .filter(start__gte=now, start__lte=soon)
        .exclude(status__in=["cancelled", "completed"])
        .order_by("start")[:8]
    )

    # Recent inquiries for the shortcut panel
    recent_inquiries = Inquiry.objects.order_by("-created_at")[:5]

    # Initial patients for the DM sidebar (show all active if field exists; else all)
    base_patients = patient_order(patient_queryset())
    if _model_has_field(Patient, "is_active"):
        base_patients = base_patients.filter(is_active=True)
    patients = base_patients[:60]

    context = {
        "profile": profile,
        "next48": next48,
        "recent_inquiries": recent_inquiries,
        "patients": patients,   # <- DM sidebar uses this
        "tab": "dm",            # optional: default the card to DM
    }
    return render(request, "reception/dashboard.html", context)


@login_required
def receptionist_profile_edit(request):
    profile, _ = ReceptionistProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ReceptionistProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            return redirect("reception:dashboard")
    else:
        form = ReceptionistProfileForm(instance=profile)

    return render(request, "reception/profile_edit.html", {"form": form, "profile": profile})


# ---------- HTMX Inquiry modal (used by the dashboard shortcut panel) ------

@login_required
@user_passes_test(is_reception)
def inquiry_modal(request, pk: int):
    inquiry = get_object_or_404(Inquiry, pk=pk)
    return render(
        request,
        "reception/partials/inquiry_modal.html",
        {"inquiry": inquiry},   # no form passed
    )


# ---------------------------------------------------------------------------
# Appointment quick actions
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_reception)
@require_POST
def appt_remind(request, pk):
    appt = get_object_or_404(
        Appointment.objects.select_related("clinician", "patient"), pk=pk
    )
    clinician_email = _clinician_email(appt.clinician)
    if clinician_email:
        send_mail(
            subject=f"Reminder: Appointment with {appt.patient} on {appt.start:%a, %b %d · %H:%M}",
            message=f"Hi,\n\nReminder for appointment: {appt}.\n\n— Nouvel EMR",
            from_email=None,
            recipient_list=[clinician_email],
            fail_silently=True,
        )
    return JsonResponse({"ok": True})


@login_required
@user_passes_test(is_reception)
@require_POST
def appt_cancel(request, pk):
    appt = get_object_or_404(Appointment, pk=pk)
    appt.status = "cancelled"
    appt.save(update_fields=["status"])

    clinician_email = _clinician_email(appt.clinician)
    if clinician_email:
        send_mail(
            subject=f"Cancelled: Appointment with {appt.patient} on {appt.start:%a, %b %d · %H:%M}",
            message="This appointment was cancelled by reception.",
            from_email=None,
            recipient_list=[clinician_email],
            fail_silently=True,
        )
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Appointments hub (lists)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_reception)
def appt_hub_clinicians(request):
    """Landing: list clinicians with counts (values() rows as dicts)."""
    now = timezone.now()
    qs = (
        Appointment.objects.select_related("clinician")
        .values(
            "clinician_id",
            "clinician__first_name",
            "clinician__last_name",
            "clinician__username",
        )
        .annotate(
            total=Count("id"),
            upcoming=Count(
                "id",
                filter=Q(start__gte=now, status__in=["confirmed", "requested"]),
            ),
            cancelled=Count("id", filter=Q(status="cancelled")),
        )
        .order_by("-upcoming", "clinician__last_name", "clinician__first_name")
    )

    paginator = Paginator(list(qs), 24)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    ctx = {"page_obj": page_obj, "clinician": None, "profile": None}
    return render(request, "reception/appt_hub_clinicians.html", ctx)


@login_required
@user_passes_test(is_reception)
def appt_hub_for_clinician(request, cid: int):
    """Detail per clinician with tabs, search, pagination, and 48h highlight."""
    now = timezone.now()
    base = Appointment.objects.select_related("patient", "clinician").filter(clinician_id=cid)

    tab = request.GET.get("tab", "upcoming")
    if tab == "requests":
        qs = base.filter(status__in=["requested", "pending"]).order_by("start")
    elif tab == "past":
        qs = base.filter(end__lt=now).exclude(status="cancelled").order_by("-start")
    elif tab == "cancelled":
        qs = base.filter(status="cancelled").order_by("-start")
    else:  # upcoming
        qs = base.filter(start__gte=now, status__in=["confirmed", "requested"]).order_by("start")

    # Search by patient name/email for both schemas
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(
            Q(patient__user__first_name__icontains=q) |
            Q(patient__user__last_name__icontains=q)  |
            Q(patient__user__username__icontains=q)   |
            Q(patient__user__email__icontains=q)      |
            Q(patient__given_name__icontains=q)       |
            Q(patient__family_name__icontains=q)      |
            Q(patient__first_name__icontains=q)       |
            Q(patient__last_name__icontains=q)        |
            Q(patient__email__icontains=q)
        )

    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    in_48h_ids = set(
        base.filter(
            start__gte=now,
            start__lte=now + timedelta(hours=48),
            status__in=["confirmed", "requested"],
        ).values_list("id", flat=True)
    )

    first = base.first()
    clinician = first.clinician if first else get_object_or_404(User, pk=cid)

    ctx = {
        "clinician_id": cid,
        "clinician": clinician,
        "tab": tab,
        "page_obj": page_obj,
        "q": q,
        "in_48h_ids": in_48h_ids,
    }
    return render(request, "reception/appt_hub_clinician.html", ctx)


@login_required
@user_passes_test(is_reception)
def clinician_availability_panel(request, cid: int):
    """Placeholder: busy blocks from existing appts next 7 days (for sidebar)."""
    start = timezone.now()
    end = start + timedelta(days=7)
    appts = Appointment.objects.filter(
        clinician_id=cid, start__gte=start, start__lt=end
    ).values_list("start", "end")
    busy = [(s, e) for s, e in appts]
    ctx = {"start": start, "end": end, "busy": busy, "clinician_id": cid}
    return render(request, "reception/partials/clinician_availability.html", ctx)


# ---------------------------------------------------------------------------
# Reception booking calendar (week view)
# ---------------------------------------------------------------------------

@login_required
@user_passes_test(is_reception)
def reception_book_calendar(request):
    """
    Reception picks clinician + patient, selects week, loads grid (HTMX).
    Reads both ?clinician and ?clinician_id (same for patient).
    """
    clinicians = _clinician_qs()

    patients_qs = patient_order(patient_queryset())
    # Build a safe "patients" list: [{id, label}] → avoids template lookups on model fields
    safe_patients = [{"id": p.pk, "label": patient_label(p)} for p in patients_qs[:200]]

    clinician_id = _safe_int(request.GET.get("clinician") or request.GET.get("clinician_id"))
    patient_id   = _safe_int(request.GET.get("patient")   or request.GET.get("patient_id"))
    week_start_str = request.GET.get("week_start")

    try:
        week_start = (
            datetime.strptime(week_start_str, "%Y-%m-%d").date()
            if week_start_str else timezone.localdate()
        )
    except (TypeError, ValueError):
        week_start = timezone.localdate()

    ctx = {
        "clinicians": clinicians,
        "patients": safe_patients,   # use safe list (id + label only)
        "clinician_id": clinician_id,
        "patient_id": patient_id,
        "week_start": week_start,
        "duration": DEFAULT_SLOT_MINUTES,
    }
    return render(request, "reception/book_calendar.html", ctx)


@login_required
@user_passes_test(is_reception)
@require_GET
def reception_book_slots_grid(request):
    """
    HTMX partial: week grid of free slots for a clinician.
    Mirrors portal's windowed call to suggest_free_slots() so results match.
    """
    clinician_id = _safe_int(request.GET.get("clinician_id") or request.GET.get("clinician"))
    duration = _safe_int(request.GET.get("duration"), DEFAULT_SLOT_MINUTES)
    week_start_str = request.GET.get("week_start")
    patient_id = request.GET.get("patient_id") or request.GET.get("patient")  # passthrough

    if not clinician_id or not week_start_str:
        return HttpResponseBadRequest("Missing clinician_id or week_start")

    try:
        week_start = datetime.fromisoformat(week_start_str).date()
    except Exception:
        return HttpResponseBadRequest("Invalid week_start")

    days = [week_start + timedelta(days=i) for i in range(7)]
    tz = timezone.get_current_timezone()

    # Build aware datetimes spanning the whole week [start, next_start)
    date_from = timezone.make_aware(datetime.combine(days[0], datetime.min.time()), tz)
    date_to   = timezone.make_aware(datetime.combine(days[-1] + timedelta(days=1), datetime.min.time()), tz)

    # Windowed call (portal style)
    try:
        slots = suggest_free_slots(
            clinician_id=int(clinician_id),
            date_from=date_from,
            date_to=date_to,
            duration_minutes=duration,
            step_minutes=None,
            patient_id=None,
            limit=500,
        )
    except TypeError:
        # Older builds may use 'max_results' instead of 'limit'
        slots = suggest_free_slots(
            clinician_id=int(clinician_id),
            date_from=date_from,
            date_to=date_to,
            duration_minutes=duration,
            step_minutes=None,
            patient_id=None,
            max_results=500,
        )
    except Exception:
        slots = []

    # Group by day + normalize for template
    slots_by_day = {d: [] for d in days}
    for s in slots or []:
        st = s["start"] if isinstance(s, dict) else getattr(s, "start", None)
        en = s.get("end") if isinstance(s, dict) else getattr(s, "end", None)
        if not st:
            continue
        if timezone.is_naive(st): st = timezone.make_aware(st, tz)
        if en and timezone.is_naive(en): en = timezone.make_aware(en, tz)
        st_local = timezone.localtime(st, tz)
        en_local = timezone.localtime(en, tz) if en else None
        day = st_local.date()
        if day in slots_by_day:
            label = f"{st_local:%H:%M} – {en_local:%H:%M}" if en_local else f"{st_local:%H:%M}"
            slots_by_day[day].append({
                "start": st.isoformat(),
                "end": (en and en.isoformat()) or "",
                "label": label,
            })

    # Sort each day’s slots
    for d in slots_by_day:
        slots_by_day[d].sort(key=lambda x: x["start"])

    # Shape rows for the partial (avoids dict indexing in templates)
    rows = [{"date": d, "slots": slots_by_day.get(d, [])} for d in days]

    html = render_to_string(
        "reception/partials/_calendar_grid.html",
        {
            "rows": rows,
            "duration": duration,
            "clinician_id": clinician_id,
            "patient_id": patient_id,
        },
        request=request,
    )
    return HttpResponse(html)


@login_required
@user_passes_test(is_reception)
@require_POST
def reception_book_create(request):
    """
    Create an appointment via the SAME pipeline as the appointments console:
    - conflict check (clinician + patient)
    - AppointmentCreateSerializer
    - audit + email/ICS
    Also records who booked it via created_by (receptionist).
    """
    patient_pk = _safe_int(request.POST.get("patient_id") or request.POST.get("patient"))
    clinician_id = _safe_int(request.POST.get("clinician_id") or request.POST.get("clinician"))
    start_iso = request.POST.get("start")
    end_iso = request.POST.get("end")

    if not all([patient_pk, clinician_id, start_iso, end_iso]):
        return HttpResponseBadRequest("Missing fields")

    # Ensure this is a real Patient id (not a User id)
    get_object_or_404(Patient, pk=patient_pk)

    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
    except ValueError:
        return HttpResponseBadRequest("start/end must be ISO 8601")

    if timezone.is_naive(start): start = timezone.make_aware(start)
    if timezone.is_naive(end):   end = timezone.make_aware(end)

    # Conflicts expect Patient.id
    conflicts = list(conflicting_appointments(
        clinician_id=int(clinician_id),
        patient_id=int(patient_pk),
        start=start,
        end=end,
    ))
    if conflicts:
        html = render_to_string("appointments/_conflict.html", {"conflicts": conflicts[:10]}, request=request)
        resp = HttpResponse(html, status=409)
        resp["HX-Trigger"] = "reception:slot-conflict"
        return resp

    payload = {
        "patient": patient_pk,     # Patient.id
        "clinician": clinician_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    ser = AppointmentCreateSerializer(data=payload)
    ser.is_valid(raise_exception=True)
    appt = ser.save()

    # Persist who booked it (so lists can show "Booked by Reception: <name>")
    if hasattr(appt, "created_by_id"):
        appt.created_by = request.user
        appt.save(update_fields=["created_by"])

    log_event(request, "appt.create.reception", "Appointment", appt.id)
    try:
        send_appointment_email.delay(appt.id, "created")
    except Exception:
        pass

    msg = f'Booked {timezone.localtime(start):%a %b %d · %H:%M}.'
    resp = HttpResponse(f'<div class="text-emerald-700 text-sm">{msg}</div>')
    resp["HX-Trigger"] = "reception:slot-booked"
    return resp


@login_required
@user_passes_test(is_reception)
@require_GET
def patient_typeahead(request):
    """
    HTMX typeahead: returns <option> list for a <datalist> based on ?q=.
    Value carries Patient.id; label shows the safest human name we can compute.
    """
    q = (request.GET.get("q") or "").strip()
    out = []
    if q:
        qs = patient_search(patient_queryset(), q)[:30]
        for p in qs:
            out.append(f'<option value="{patient_id(p)}">{patient_label(p)}</option>')
    return HttpResponse("".join(out))


# ---------------------------------------------------------------------------
# Direct Messages (Reception ↔ Patient)
# ---------------------------------------------------------------------------

# Try to import a messaging model if present; otherwise we’ll render-only.
try:
    from apps.messaging.models import DirectMessage  # adjust to your real model if different
except Exception:  # pragma: no cover - optional app
    DirectMessage = None


@login_required
@user_passes_test(is_reception)
@require_GET
def dm_thread(request):
    """
    Load the message thread with a patient for reception users.
    Returns HTML for the thread (used by HTMX).
    """
    pid = request.GET.get("patient_id")
    if not pid:
        return HttpResponseBadRequest("patient_id required")

    patient = get_object_or_404(Patient, pk=pid)

    msgs = []
    if DirectMessage:
        # Assumptions: DirectMessage has fields (patient, sender, body, created_at)
        msgs = (
            DirectMessage.objects
            .filter(patient_id=patient.pk)
            .select_related("sender")
            .order_by("created_at")[:200]
        )

    ctx = {"patient": patient, "msgs": msgs}
    return TemplateResponse(request, "reception/partials/dm_thread.html", ctx)


@login_required
@user_passes_test(is_reception)
@require_POST
def dm_send(request):
    """
    Send a DM from receptionist to a patient. Returns a single message bubble HTML to append.
    """
    pid  = request.POST.get("patient_id")
    body = (request.POST.get("body") or "").strip()
    if not pid or not body:
        return HttpResponseBadRequest("patient_id and body required")

    patient = get_object_or_404(Patient, pk=pid)

    # Persist if messaging model exists; otherwise build a transient object for rendering
    if DirectMessage:
        try:
            m = DirectMessage.objects.create(
                patient=patient,
                sender=request.user,
                body=body,
                created_at=timezone.now(),
            )
        except Exception:
            # If fields differ in your model, adjust here.
            return HttpResponseBadRequest("Failed to create message (schema mismatch).")
    else:
        # Minimal shim with attributes the template expects
        class _Msg:
            def __init__(self, sender, body):
                self.sender = sender
                self.sender_id = sender.id
                self.body = body
                self.created_at = timezone.now()
        m = _Msg(request.user, body)

    return TemplateResponse(request, "reception/partials/dm_message.html", {"m": m})



