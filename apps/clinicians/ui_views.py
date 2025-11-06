# apps/clinicians/ui_views.py
from __future__ import annotations

from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.db.models import Q, Count
from django.http import HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.utils import timezone
from django.template import loader
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.appointments.models import Appointment
from apps.messaging.models import Message
from apps.patients.models import Patient

from django import forms
from django.views.decorators.http import require_http_methods
from apps.appointments.models import Availability
from apps.appointments.services import suggest_free_slots

from django.shortcuts import get_object_or_404, redirect

import io  
from django.http import FileResponse, JsonResponse  


from reportlab.lib.pagesizes import A4  
from reportlab.lib import colors         
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle  
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle  

from apps.prescriptions.models import Prescription
from django.conf import settings
from django.template.loader import render_to_string
from django.template.loader import select_template
from django.contrib.staticfiles.storage import staticfiles_storage
from django.contrib.staticfiles import finders





# ----------------------------- helpers ------------------------------------- #




def _to_int(value, default: int, *, min_value: int = 1, max_value: int | None = 100) -> int:
    """Parse integers from query params safely."""
    try:
        i = int(value)
    except (TypeError, ValueError):
        return default
    if i < min_value:
        return default
    if max_value is not None and i > max_value:
        i = max_value
    return i


def _parse_date(val: str | None):
    if not val:
        return None
    try:
        # YYYY-MM-DD
        return datetime.strptime(val, "%Y-%m-%d").date()
    except Exception:
        return None


def _assert_can_view(request, clinician: User):
    """
    Allow if the current user is the clinician themselves OR a superuser.
    Raise 403 otherwise.
    """
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        raise PermissionDenied("You do not have access to this dashboard.")


def _derive_status(appt: Appointment, now):
    """
    Return one of: 'upcoming' | 'attended' | 'cancelled'.
    Works even if your model doesn't have a formal 'status' field.
    """
    if hasattr(appt, "status") and appt.status:
        s = str(appt.status).lower()
        if "cancel" in s:
            return "cancelled"
        if s in {"attended", "done", "completed", "complete"}:
            return "attended"
    return "attended" if getattr(appt, "start", None) and appt.start < now else "upcoming"


def _get_rx_for_clinician_or_404(clinician_id: int, rx_id: int) -> Prescription:
    return get_object_or_404(Prescription, pk=rx_id, clinician_id=clinician_id)

# ----------------------------- Tests (See all) ------------------------------ #

@login_required
def tests_index(request, pk):
    """Full-page Tests index; table hydrates via HTMX."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    try:
        from apps.documents.models import Document
        docs = (
            Document.objects
            .filter(kind__in=["lab_result", "test_result"])
            .select_related("patient")
            .order_by("-created_at")[:25]
        )
    except Exception:
        docs = []

    return render(
        request,
        "clinicians/console/tests_index.html",
        {"clinician": clinician, "initial_docs": docs},
    )


@login_required
def tests_table(request, pk):
    """HTMX endpoint to render the tests table with filters/paging."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()
    kind = (request.GET.get("kind") or "all").strip().lower()  # all|lab_result|test_result
    patient = (request.GET.get("patient") or "").strip()
    date_from = _parse_date(request.GET.get("date_from"))
    date_to   = _parse_date(request.GET.get("date_to"))

    limit  = _to_int(request.GET.get("limit"), 25, min_value=5, max_value=100)
    offset = _to_int(request.GET.get("offset"), 0,  min_value=0,  max_value=100_000)

    try:
        from apps.documents.models import Document

        qs = (
            Document.objects
            .filter(kind__in=["lab_result", "test_result"])
            .select_related("patient")
        )

        if kind in {"lab_result", "test_result"}:
            qs = qs.filter(kind=kind)

        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(filename__icontains=q) |
                Q(patient__family_name__icontains=q) |
                Q(patient__given_name__icontains=q) |
                Q(patient__email__icontains=q) |
                Q(patient__phone__icontains=q)
            )

        if patient:
            qs = qs.filter(
                Q(patient__family_name__icontains=patient) |
                Q(patient__given_name__icontains=patient) |
                Q(patient__email__icontains=patient) |
                Q(patient__phone__icontains=patient)
            )

        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        qs = qs.order_by("-created_at")
        total = qs.count()
        rows = list(qs[offset: offset + limit])
    except Exception:
        total = 0
        rows = []

    ctx = {
        "docs": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
        "next_offset": offset + limit if offset + limit < total else None,
        "prev_offset": offset - limit if offset - limit >= 0 else None,
        "q": q,
        "kind": kind,
        "patient": patient,
        "date_from": request.GET.get("date_from") or "",
        "date_to": request.GET.get("date_to") or "",
        "clinician": clinician,
    }
    return render(request, "clinicians/partials/tests_table.html", ctx)


# ----------------------------- pages --------------------------------------- #

@login_required
def dashboard(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    docs_href     = reverse("documents_ui:list", args=[clinician.pk])
    rx_list_href  = reverse("prescriptions_ui:list", args=[clinician.pk])
    enc_href      = reverse("encounters_ui:list", args=[clinician.pk])
    patients_href = reverse("patients_ui:patients_home")
    consults_href = reverse("clinicians_ui:consultations_all", args=[clinician.pk])
    availability_href = reverse("clinicians_ui:availability_index", args=[clinician.pk])
    lab_href = reverse("labs_ui:lab_index", args=[clinician.pk])

    # Prefer full â€œSee all testsâ€ page; fall back to mini-card endpoint if missing
    try:
        tests_href = reverse("clinicians_ui:tests_index", args=[clinician.pk])
    except Exception:
        tests_href = reverse("clinicians_ui:tests", args=[clinician.pk])

    shortcuts = [
        {"label": "Consultation", "icon": "calculator.svg", "href": consults_href, "accent": "teal"},
        {"label": "Prescription", "icon": "pencil.svg",     "href": rx_list_href,  "accent": "teal"},
        {"label": "Document",     "icon": "doc.svg",        "href": docs_href,     "accent": "teal"},
        {"label": "Encounter",    "icon": "people.svg",     "href": enc_href,      "accent": "teal"},
        {"label": "Patients",     "icon": "user.svg",       "href": patients_href, "accent": "teal"},
        {"label": "Availability", "icon": "pencil.svg",     "href": availability_href, "accent": "red"},
       {"label": "Lab", "icon": "pencil.svg", "href": lab_href, "accent": "red"}
    ]

    # Mobile dock: two primary actions + rest in off-canvas
    primary_indices = [1, len(shortcuts) - 1]  # Prescription, Tests
    primary_shortcuts = [shortcuts[i] for i in primary_indices if 0 <= i < len(shortcuts)]
    if len(primary_shortcuts) < 2:
        for s in shortcuts:
            if s not in primary_shortcuts:
                primary_shortcuts.append(s)
            if len(primary_shortcuts) == 2:
                break
    more_shortcuts = [s for s in shortcuts if s not in primary_shortcuts]

    return render(
        request,
        "clinicians/console/dashboard.html",
        {
            "clinician": clinician,
            "shortcuts": shortcuts,
            "primary_shortcuts": primary_shortcuts,
            "more_shortcuts": more_shortcuts,
        },
    )


@login_required
def consultations_all(request, pk):
    """
    Clinician â€œSee allâ€ consultations list.

    Filters:
      - ?status=all|upcoming|past|cancelled
      - ?q=<patient name/email/phone>
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "all").strip().lower()

    # Base queryset: this clinicianâ€™s appointments
    qs = (
        Appointment.objects
        .filter(clinician=clinician)
        .select_related("patient")
    )

    # Search by patient fields
    if q:
        qs = qs.filter(
            Q(patient__given_name__icontains=q) |
            Q(patient__family_name__icontains=q) |
            Q(patient__email__icontains=q) |
            Q(patient__phone__icontains=q)
        )

    # Status/time filters
    now = timezone.now()
    has_start = hasattr(Appointment, "start")
    has_status = hasattr(Appointment, "status")

    if status == "upcoming" and has_start:
        qs = qs.filter(start__gte=now)
    elif status == "past" and has_start:
        qs = qs.filter(start__lt=now)
    elif status == "cancelled" and has_status:
        qs = qs.filter(status__iexact="cancelled")
    else:
        if has_status:
            qs = qs.exclude(status__iexact="cancelled")

    # Ordering
    qs = qs.order_by("-start") if has_start else qs.order_by("-id")

    # Fetch
    appts = list(qs[:200])

    # Build the structure your template expects
    items = [{"obj": a, "status": _derive_status(a, now)} for a in appts]

    tabs = [
        ("all", "All"),
        ("upcoming", "Upcoming"),
        ("past", "Past"),
        ("cancelled", "Cancelled"),
    ]

    return render(
        request,
        "clinicians/console/consultations_all.html",
        {
            "clinician": clinician,
            "q": q,
            "status": status,
            "tabs": tabs,
            "appts": appts,
            "items": items,
            "now": now,  
        },
    )


@login_required
def upcoming(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    now = timezone.now()
    end = now + timedelta(hours=48)  # <-- 48h window

    qs = (
        Appointment.objects
        .filter(clinician=clinician, start__gte=now, start__lte=end)
        .exclude(status__in=["canceled", "cancelled"])
        .select_related("patient")
        .order_by("start")
    )

    # compute total consultations (unchanged)
    total_consultations = (
        Appointment.objects
        .filter(clinician=clinician)
        .exclude(status__in=["canceled", "cancelled"])
        .count()
    )

    appts = list(qs[:3])          # <-- cap at 3
    appts_count = qs.count()       # count within 48h (not just the 3)

    return render(
        request,
        "clinicians/partials/upcoming.html",
        {
            "clinician": clinician,
            "appts": appts,
            "appts_count": appts_count,
            "total_consultations": total_consultations,
            "now": now,  # for cancel button condition
        },
    )



@login_required
def tests(request, pk):
    """Small Tests card on dashboard (recent few)."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    q = (request.GET.get("q") or "").strip()

    try:
        from apps.documents.models import Document
        docs = (
            Document.objects
            .filter(kind__in=["lab_result", "test_result"])
            .select_related("patient")
            .order_by("-created_at")
        )
        if q:
            docs = docs.filter(
                Q(title__icontains=q) |
                Q(filename__icontains=q) |
                Q(patient__family_name__icontains=q) |
                Q(patient__given_name__icontains=q) |
                Q(patient__email__icontains=q) |
                Q(patient__phone__icontains=q)
            )
        docs = docs[:20]
    except Exception:
        docs = []

    return render(
        request,
        "clinicians/partials/tests.html",
        {"docs": docs, "q": q, "clinician": clinician},
    )


@login_required
def inbox(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    msgs = Message.objects.filter(to_user_id=pk, kind="inbox")[:20]
    return render(
        request,
        "clinicians/partials/inbox.html",
        {"msgs": msgs, "tab": "inbox", "clinician": clinician},
    )


def _patient_user_or_none(patient):
    email = (patient.email or "").strip().lower()
    if not email:
        return None
    UserModel = get_user_model()
    try:
        return UserModel.objects.get(email__iexact=email)
    except UserModel.DoesNotExist:
        return None


@login_required
def direct_messages(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    patients = (
        Patient.objects
        .filter(is_active=True, merged_into__isnull=True)
        .order_by("family_name", "given_name", "id")[:80]
    )

    # --- prep unread counts per patient (patient -> clinician) ---
    # map portal user ids for these patients
    p_users = {}
    for p in patients:
        pu = _patient_user_or_none(p)
        if pu:
            p_users[p.id] = pu.id

    if p_users:
        rows = (
            Message.objects.filter(
                kind="dm",
                to_user_id=clinician.id,
                is_read=False,
                from_user_id__in=list(p_users.values()),
            )
            .values("from_user_id")
            .annotate(cnt=Count("id"))
        )
        by_uid = {r["from_user_id"]: r["cnt"] for r in rows}
        for p in patients:
            puid = p_users.get(p.id)
            p.unread_count = by_uid.get(puid, 0)
    else:
        for p in patients:
            p.unread_count = 0

    msgs = Message.objects.filter(to_user_id=pk, kind="dm").order_by("-id")[:20]
    return render(
        request,
        "clinicians/partials/inbox.html",
        {"msgs": msgs, "tab": "dm", "clinician": clinician, "patients": patients},
    )


@login_required
def dm_thread(request, pk):
    """Return conversation thread HTML (HTMX) and mark incoming unread as read."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    pid = request.GET.get("patient_id")
    patient = get_object_or_404(Patient, pk=pid)
    p_user = _patient_user_or_none(patient)
    thread = []

    if p_user:
        # mark incoming unread as read (patient -> clinician)
        Message.objects.filter(
            kind="dm",
            from_user_id=p_user.id,
            to_user_id=clinician.id,
            is_read=False,
        ).update(is_read=True)

        thread = (
            Message.objects.filter(kind="dm")
            .filter(
                (Q(from_user_id=clinician.pk) & Q(to_user_id=p_user.pk)) |
                (Q(from_user_id=p_user.pk) & Q(to_user_id=clinician.pk))
            )
            .order_by("id")[:200]
        )

    resp = render(
        request,
        "clinicians/partials/_dm_thread.html",
        {"msgs": thread, "patient": patient, "p_user": p_user, "clinician": clinician},
    )
    # tell navbar badge to refresh
    resp["HX-Trigger"] = '{"refresh-badges": true}'
    return resp


@login_required
def dm_send(request, pk):
    """Handle send (HTMX) for DMs."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    pid = request.POST.get("patient_id")
    body = (request.POST.get("body") or "").strip()
    if not pid or not body:
        return HttpResponseBadRequest("Missing fields")

    patient = get_object_or_404(Patient, pk=pid)
    p_user = _patient_user_or_none(patient)
    if not p_user:
        return HttpResponseBadRequest("Patient has no portal user/email.")

    msg = Message.objects.create(
        kind="dm",
        from_user=clinician,
        to_user=p_user,
        subject="",
        body=body,
        is_read=False,  # unread for the patient
    )

    is_me = (msg.from_user_id == clinician.id)

    resp = render(
        request,
        "clinicians/partials/_dm_msg.html",
        {"m": msg, "clinician": clinician, "is_me": is_me},
    )
    # tell navbar badge to refresh (in case we later count sent-but-unread on clinician side too)
    resp["HX-Trigger"] = '{"refresh-badges": true}'
    return resp


@require_POST
@login_required
def cancel_appt(request, pk, appt_pk):
    """
    Marks an appointment as cancelled. If called via HTMX from the dashboard,
    returns the refreshed upcoming panel; otherwise redirects back to the list.
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    appt = get_object_or_404(Appointment, pk=appt_pk, clinician_id=pk)

    # Update status if not already cancelled
    current = (getattr(appt, "status", "") or "").lower()
    if current not in ("canceled", "cancelled"):
        if hasattr(appt, "status"):
            appt.status = "cancelled"
            appt.save(update_fields=["status"])
        else:
            appt.save()

        # Optional side-effects
        try:
            from apps.audit.utils import log_event
            log_event(request, "appt.cancel.ui", "Appointment", appt.id)
        except Exception:
            pass
        try:
            from apps.appointments.tasks import send_appointment_email
            send_appointment_email.delay(appt.id, "canceled")
        except Exception:
            pass

    # HTMX? return refreshed upcoming; else redirect to list
    if request.headers.get("HX-Request"):
        return upcoming(request, pk)
    return redirect(reverse("clinicians_ui:consultations_all", args=[pk]))


@login_required
def edit_profile(request, pk):
    """
    Simple, safe edit page for clinicians.
    Allows self-edit (or superuser) and only updates fields that exist.
    Also supports avatar stored either on User.avatar or on related Profile.avatar.
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)

    # Only the owner or a superuser can edit
    if not (request.user.is_superuser or request.user.pk == clinician.pk):
        raise PermissionDenied("You cannot edit this profile.")

    # Detect optional fields
    supports = {
        "phone": hasattr(clinician, "phone"),
        "specialty": hasattr(clinician, "specialty"),
        "bio": hasattr(clinician, "bio"),
        "timezone": hasattr(clinician, "timezone"),
        "avatar": hasattr(clinician, "avatar"),  # avatar on the User model
        "profile": hasattr(clinician, "profile"),
        "profile_avatar": hasattr(clinician, "profile") and hasattr(getattr(clinician, "profile"), "avatar"),
    }

    if request.method == "POST":
        first_name = (request.POST.get("first_name") or "").strip()
        last_name  = (request.POST.get("last_name") or "").strip()
        email      = (request.POST.get("email") or "").strip()

        errs = []
        if not first_name: errs.append("First name is required.")
        if not last_name:  errs.append("Last name is required.")
        if not email:      errs.append("Email is required.")

        phone     = (request.POST.get("phone") or "").strip()
        specialty = (request.POST.get("specialty") or "").strip()
        bio       = (request.POST.get("bio") or "").strip()
        tz        = (request.POST.get("timezone") or "").strip()

        if errs:
            messages.error(request, " ".join(errs))
        else:
            # Core fields
            clinician.first_name = first_name
            clinician.last_name  = last_name
            clinician.email      = email

            # Optionals
            if supports["phone"]:
                setattr(clinician, "phone", phone)
            if supports["specialty"]:
                setattr(clinician, "specialty", specialty)
            if supports["bio"]:
                setattr(clinician, "bio", bio)
            if supports["timezone"] and tz:
                setattr(clinician, "timezone", tz)

            # --- Avatar handling ---
            new_avatar = request.FILES.get("avatar")
            if new_avatar:
                if supports["avatar"]:
                    # Avatar lives on User
                    setattr(clinician, "avatar", new_avatar)
                else:
                    # Avatar lives on Profile (create if missing)
                    ProfileModel = None
                    if supports["profile"]:
                        prof = getattr(clinician, "profile")
                        if prof is None:
                            try:
                                ProfileModel = prof.__class__
                            except Exception:
                                ProfileModel = None
                            if ProfileModel is None:
                                try:
                                    from apps.accounts.models import Profile as ProfileModel  # type: ignore
                                except Exception:
                                    ProfileModel = None
                            if ProfileModel:
                                prof = ProfileModel.objects.create(user=clinician)
                                setattr(clinician, "profile", prof)
                        if prof and hasattr(prof, "avatar"):
                            prof.avatar = new_avatar
                            prof.save(update_fields=["avatar"])
                        else:
                            messages.warning(request, "Avatar field not found on profile; skipped.")
                    else:
                        messages.warning(request, "No avatar field on User or Profile; skipped.")

            try:
                clinician.save()
                messages.success(request, "Profile updated.")
                return redirect("clinicians_ui:dashboard", pk=clinician.pk)
            except Exception as e:
                messages.error(request, f"Could not save profile: {e}")

    # Recompute supports for template (safe)
    supports = {
        "phone": hasattr(clinician, "phone"),
        "specialty": hasattr(clinician, "specialty"),
        "bio": hasattr(clinician, "bio"),
        "timezone": hasattr(clinician, "timezone"),
        "avatar": hasattr(clinician, "avatar"),
    }

    return render(
        request,
        "clinicians/console/edit_profile.html",
        {"clinician": clinician, "supports": supports},
    )


# -------- Superuser utilities --------

@user_passes_test(lambda u: u.is_superuser)
def list_clinicians(request):
    qs = User.objects.filter(is_staff=True).order_by("first_name", "last_name", "id")
    return render(request, "clinicians/console/list.html", {"clinicians": qs})


# ----------------------------- NEW: navbar badge ---------------------------- #

@login_required
def unread_badge(request, pk):
    """
    Tiny badge partial with total unread DMs for this clinician.
    Use in navbar with hx-get + hx-trigger="load, every 10s, refresh-badges from:body".
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    total = Message.objects.filter(
        to_user_id=clinician.id,
        is_read=False,
        kind="dm",
    ).count()

    tmpl = loader.get_template("clinicians/partials/_inbox_badge.html")
    html = tmpl.render({"total": total}, request)
    return HttpResponse(html)


class AvailabilityForm(forms.ModelForm):
    class Meta:
        model = Availability
        fields = ["weekday", "start_time", "end_time", "slot_minutes", "is_active"]
        widgets = {
            "weekday":      forms.Select(attrs={"class": "w-full rounded-xl border border-black/10 bg-white px-3 py-2"}),
            "start_time":   forms.TimeInput(attrs={"type": "time", "class": "w-full rounded-xl border border-black/10 bg-white px-3 py-2"}),
            "end_time":     forms.TimeInput(attrs={"type": "time", "class": "w-full rounded-xl border border-black/10 bg-white px-3 py-2"}),
            "slot_minutes": forms.NumberInput(attrs={"class": "w-full rounded-xl border border-black/10 bg-white px-3 py-2", "min": 5, "step": 5}),
            "is_active":    forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
        }

# ----------------------------- Availability: pages ------------------------- #

@login_required
def availability_index(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    windows = (Availability.objects
               .filter(clinician=clinician)
               .order_by("weekday", "start_time"))
    by_day = {i: [] for i in range(7)}
    for w in windows:
        by_day[w.weekday].append(w)

    now = timezone.now()
    preview = suggest_free_slots(
        clinician_id=clinician.id,
        date_from=now,
        date_to=now + timedelta(days=7),
        duration_minutes=30,
        step_minutes=None,
        patient_id=None,
        limit=12,
    )

    return render(request, "clinicians/console/availability_index.html", {
        "clinician": clinician,
        "windows_by_day": by_day,
        "form": AvailabilityForm(),
        "preview": preview,
        "now": now,
    })

@login_required
def availability_list_partial(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    windows = (Availability.objects
               .filter(clinician=clinician)
               .order_by("weekday", "start_time"))

    by_day = {i: [] for i in range(7)}
    for w in windows:
        by_day[w.weekday].append(w)

    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    days = [{"idx": i, "label": labels[i], "windows": by_day[i]} for i in range(7)]

    return render(request, "clinicians/partials/availability_list.html", {
        "clinician": clinician,
        "days": days,
    })

@login_required
def availability_preview_partial(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    now = timezone.now()
    df = request.GET.get("date_from")
    dt = request.GET.get("date_to")
    dur = int(request.GET.get("duration", 30) or 30)
    step = request.GET.get("step")
    step_i = int(step) if step else None

    date_from = timezone.make_aware(timezone.datetime.fromisoformat(df)) if df else now
    date_to   = timezone.make_aware(timezone.datetime.fromisoformat(dt)) if dt else now + timedelta(days=7)

    slots = suggest_free_slots(
        clinician_id=clinician.id,
        date_from=date_from,
        date_to=date_to,
        duration_minutes=dur,
        step_minutes=step_i,
        patient_id=None,
        limit=24,
    )

    return render(request, "clinicians/partials/availability_preview.html", {
        "slots": slots,
        "clinician": clinician,
    })

@login_required
@require_http_methods(["GET","POST"])
def availability_new(request, pk):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    if request.method == "POST":
        form = AvailabilityForm(request.POST)
        if form.is_valid():
            av = form.save(commit=False)
            av.clinician = clinician
            av.save()
            if request.headers.get("HX-Request"):
                resp = availability_list_partial(request, pk)
                resp["HX-Trigger"] = '{"availability:close": true, "availability:refresh-preview": true}'
                return resp
            return redirect("clinicians_ui:availability_index", pk=pk)
    else:
        form = AvailabilityForm()

    return render(request, "clinicians/partials/availability_form.html", {
        "form": form,
        "clinician": clinician,
        "mode": "create",
    })

@login_required
@require_http_methods(["GET","POST"])
def availability_edit(request, pk, avail_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    av = get_object_or_404(Availability, pk=avail_id, clinician=clinician)

    if request.method == "POST":
        form = AvailabilityForm(request.POST, instance=av)
        if form.is_valid():
            form.save()
            if request.headers.get("HX-Request"):
                resp = availability_list_partial(request, pk)
                resp["HX-Trigger"] = '{"availability:close": true, "availability:refresh-preview": true}'
                return resp
            return redirect("clinicians_ui:availability_index", pk=pk)
    else:
        form = AvailabilityForm(instance=av)

    return render(request, "clinicians/partials/availability_form.html", {
        "form": form,
        "clinician": clinician,
        "mode": "edit",
        "av": av,
    })

@login_required
@require_http_methods(["POST"])
def availability_delete(request, pk, avail_id):
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)

    av = get_object_or_404(Availability, pk=avail_id, clinician=clinician)
    av.delete()

    if request.headers.get("HX-Request"):
        resp = availability_list_partial(request, pk)
        resp["HX-Trigger"] = '{"availability:close": true, "availability:refresh-preview": true}'
        return resp

    return redirect("clinicians_ui:availability_index", pk=pk)

def _pick_confirmed_status():
    """
    Choose a valid non-null 'confirmed' status based on the model's choices.
    Prefers 'scheduled' → 'confirmed' → 'approved' (case-insensitive).
    Falls back to the first non-cancel/request choice.
    """
    try:
        fld = Appointment._meta.get_field("status")
    except Exception:
        return "scheduled"

    choices = [v for v, _ in getattr(fld, "choices", [])] or []
    if not choices:
        return "scheduled"

    norm = {str(v).lower(): v for v in choices}
    for key in ("scheduled", "confirmed", "approved"):
        if key in norm:
            return norm[key]

   
    for v in choices:
        lv = str(v).lower()
        if all(t not in lv for t in ("request", "pending", "cancel")):
            return v

    
    return choices[0]


def _pick_cancelled_status():
    """Choose a valid 'cancelled' value respecting choices if present."""
    try:
        fld = Appointment._meta.get_field("status")
    except Exception:
        return "cancelled"

    choices = [v for v, _ in getattr(fld, "choices", [])] or []
    if not choices:
        return "cancelled"

    norm = {str(v).lower(): v for v in choices}
    for key in ("cancelled", "canceled"):
        if key in norm:
            return norm[key]
    return choices[-1]  


@login_required
@require_POST
def approve_request(request, pk, appt_id):
    """Clinician approves a 'requested' appointment -> set to a valid confirmed status."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    appt = get_object_or_404(Appointment, pk=appt_id, clinician=clinician)

    confirmed = _pick_confirmed_status()
    appt.status = confirmed
    appt.save(update_fields=["status"])

    back = reverse("clinicians_ui:consultations_all", args=[clinician.pk])
    qs = request.GET.urlencode()
    return redirect(f"{back}?{qs}" if qs else back)


@login_required
@require_POST
def decline_request(request, pk, appt_id):
    """Clinician declines a 'requested' appointment -> set to a valid cancelled status."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    appt = get_object_or_404(Appointment, pk=appt_id, clinician=clinician)

    cancelled = _pick_cancelled_status()
    appt.status = cancelled
    appt.save(update_fields=["status"])

    back = reverse("clinicians_ui:consultations_all", args=[clinician.pk])
    qs = request.GET.urlencode()
    return redirect(f"{back}?{qs}" if qs else back)


def _rx_qs_for_clinician(clinician):
    """Return a safe queryset for prescriptions belonging to this clinician."""
    try:
        from apps.prescriptions.models import Prescription
    except Exception:
        return []
    try:
        return (Prescription.objects
                .filter(clinician=clinician)
                .select_related("patient")
                .order_by("-created_at"))
    except Exception:
        return []

@login_required
def rx_list(request, pk):
    """Full list page (reuses your template) with the new modal/view wiring."""
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    prescriptions = list(_rx_qs_for_clinician(clinician)[:200])
    return render(
        request,
        "clinicians/prescriptions/list.html",
        {"clinician": clinician, "prescriptions": prescriptions},
    )

@login_required
@require_http_methods(["GET"])
def rx_view_modal(request, pk: int, rx_id: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True, is_active=True)
    rx = _get_rx_for_clinician_or_404(pk, rx_id)

    html = loader.render_to_string(
       "clinicians/prescriptions/_view_modal.html",
         {"clinician": clinician, "rx": rx},
        request,
    )
    return HttpResponse(html)

@login_required
def rx_download(request, pk: int, rx_id: int):
    """
    Clinician-side PDF download for a prescription.
    1) Try ReportLab (pure Python, no native deps) -> PDF
    2) Fallback to WeasyPrint (if installed) -> PDF
    3) Final fallback -> .txt
    """
    # Ensure clinician exists and caller can view
    clinician = get_object_or_404(User, pk=pk, is_staff=True, is_active=True)
    _assert_can_view(request, clinician)

    # Get Prescription for this clinician
    try:
        from apps.prescriptions.models import Prescription
    except Exception:
        return HttpResponseBadRequest("Prescriptions module not installed.")
    rx = get_object_or_404(Prescription, pk=rx_id, clinician=clinician)

    # Normalize fields
    title = getattr(rx, "title", "") or f"Prescription {rx.id}"
    body  = getattr(rx, "body", None)
    if body is None:
        body = getattr(rx, "text", "")  # soft fallback

    patient = getattr(rx, "patient", None)
    patient_name = (
        getattr(patient, "get_full_name", lambda: "")()
        or getattr(patient, "full_name", "")
        or f"{getattr(patient, 'given_name', '')} {getattr(patient, 'family_name', '')}".strip()
        or (str(patient) if patient else "")
    )

    created = getattr(rx, "created_at", None) or timezone.now()
    clinician_name = clinician.get_full_name() or clinician.username or "Clinician"
    filename = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip() or f"prescription-{rx.id}"

    # ---------- 1) Prefer ReportLab (pure Python, reliable everywhere) ----------
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
        H1   = ParagraphStyle("H1",   parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=6)
        Meta = ParagraphStyle("Meta", parent=styles["Normal"],   fontSize=9.5, textColor=colors.HexColor("#475569"))
        Body = ParagraphStyle("Body", parent=styles["Normal"],   fontSize=11.5, leading=16)
        Box  = ParagraphStyle(
            "Box", parent=styles["Normal"],
            backColor=colors.HexColor("#f8fafc"),
            borderColor=colors.HexColor("#e5e7eb"),
            borderWidth=1, borderPadding=8,
            fontSize=11.5, leading=16
        )
        Pill = ParagraphStyle(
            "Pill", parent=styles["Normal"],
            textColor=colors.white, backColor=colors.HexColor("#059669"),
            fontName="Helvetica-Bold", fontSize=9, leading=12, alignment=1
        )

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
            [Paragraph("<b>Patient:</b> " + (patient_name or ""), Body),
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
        pass  # If ReportLab not installed/available, try WeasyPrint next.

    # ---------- 2) Try WeasyPrint (if it's installed & system deps available) ----------
    try:
        from weasyprint import HTML, CSS

        html = render_to_string(
            "portal/prescriptions/pdf.html",  # reuse the same pretty template you’re using in the portal
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
        pass  # If WeasyPrint fails, fall back to plain text last.

    # ---------- 3) Final fallback: plain text ----------
    lines = [
        f"Title: {title}",
        f"Clinician: {clinician_name}",
        f"Date: {created.strftime('%Y-%m-%d %H:%M')}",
        "",
        "Prescription:",
        body or "",
        "",
    ]
    content = "\n".join(lines).strip() + "\n"
    resp = HttpResponse(content, content_type="text/plain; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}.txt"'
    return resp

@login_required
def rx_share_link(request, pk, rx_id):
    """
    Return JSON with a shareable link (e.g., to the patient portal detail page).
    Your routing may differ; adjust as needed.
    """
    clinician = get_object_or_404(User, pk=pk, is_staff=True)
    _assert_can_view(request, clinician)
    try:
        from apps.prescriptions.models import Prescription
        rx = get_object_or_404(Prescription, pk=rx_id, clinician=clinician)
    except Exception:
        return JsonResponse({"ok": False, "error": "Not found."}, status=404)

    # If you expose a patient-portal view:
    try:
        share_url = request.build_absolute_uri(reverse("portal_ui:rx_detail", args=[rx.id]))
    except Exception:
        # Fallback to a clinician-visible URL
        share_url = request.build_absolute_uri(reverse("clinicians_ui:rx_download", args=[clinician.pk, rx.id]))

    return JsonResponse({"ok": True, "url": share_url})


@login_required
@require_http_methods(["GET", "POST"])
def rx_edit(request, pk: int, rx_id: int):
    clinician = get_object_or_404(User, pk=pk, is_staff=True, is_active=True)
    if request.user != clinician and not request.user.is_superuser:
        return redirect("clinicians_ui:rx_list", pk=pk)

    rx = _get_rx_for_clinician_or_404(pk, rx_id)

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        body  = (request.POST.get("body")  or "").strip()
        patient_id = request.POST.get("patient_id")

        if title:
            rx.title = title
        rx.body = body

        if patient_id:
            try:
                rx.patient = Patient.objects.get(pk=int(patient_id))
            except Patient.DoesNotExist:
                pass

        if hasattr(rx, "updated_at"):
            from django.utils import timezone
            rx.updated_at = timezone.now()

        rx.save()
        messages.success(request, "Prescription updated.")
        return redirect("clinicians_ui:rx_list", pk=pk)

    # GET -> modal
    patients = Patient.objects.filter(is_active=True).order_by("family_name", "given_name")  # <-- fixed fields
    return render(
        request,
        "clinicians/prescriptions/_edit_modal.html",
       {"clinician": clinician, "rx": rx, "patients": patients},
    )

    # --- RX PDF generator (same look as portal) ---


def _rx_pdf_bytes(rx, logo_url: str | None = None) -> bytes:
    """
    Return PDF bytes for a prescription using a clean, branded layout.
    Pure ReportLab (no native libs required).
    """
    # Lazy imports so app loads even if reportlab not installed in some envs
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm

    title = getattr(rx, "title", "") or f"Prescription #{rx.id}"
    body  = getattr(rx, "body", None) or getattr(rx, "text", "") or ""
    clinician = getattr(rx, "clinician", None)
    clin_name = (
        getattr(clinician, "get_full_name", lambda: "")() or
        getattr(clinician, "username", "") or
        "Clinician"
    )
    created = getattr(rx, "created_at", None) or timezone.now()
    patient = getattr(rx, "patient", None)
    patient_name = ""
    if patient:
        # prefer get_full_name, fall back to given/family_name
        if hasattr(patient, "get_full_name") and patient.get_full_name():
            patient_name = patient.get_full_name()
        else:
            given = getattr(patient, "given_name", "") or ""
            family = getattr(patient, "family_name", "") or ""
            patient_name = (given + " " + family).strip() or str(patient)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16*mm, rightMargin=16*mm,
        topMargin=18*mm, bottomMargin=16*mm
    )

    styles = getSampleStyleSheet()
    H1   = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, leading=20, spaceAfter=8)
    Meta = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9.5, textColor=colors.HexColor("#475569"))
    Body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=11.5, leading=16)
    Label= ParagraphStyle("Label", parent=styles["Normal"], fontSize=10.5, textColor=colors.HexColor("#0f172a"))
    Pill = ParagraphStyle("Pill",  parent=styles["Normal"], fontSize=9, textColor=colors.white)

    story = []

    # Header (brand + pill)
    story.append(Paragraph("Nouvel — Prescription", H1))
    story.append(Paragraph(created.strftime("%Y-%m-%d %H:%M"), Meta))
    story.append(Spacer(1, 6))

    # Meta grid (2 columns)
    data = [
        [Paragraph("<b>Patient:</b> "   + (patient_name or "-"), Label),
         Paragraph("<b>Clinician:</b> " + clin_name,            Label)],
        [Paragraph("<b>Title:</b> "     + title,                Label),
         Paragraph("<b>Date:</b> "      + created.strftime("%a, %b %d %Y · %H:%M"), Label)]
    ]
    table = Table(data, colWidths=[None, None])
    table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING", (0,0), (-1,-1), 0),
        ("RIGHTPADDING",(0,0), (-1,-1), 6),
        ("BOTTOMPADDING",(0,0), (-1,-1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    # Body box
    story.append(Paragraph("<b>Instructions / Medications</b>", Label))
    # A light shaded box look
    story.append(Spacer(1, 3))
    story.append(Table(
        [[Paragraph(body.replace("\n", "<br/>"), Body)]],
        style=TableStyle([
            ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#f8fafc")),
            ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#e5e7eb")),
            ("INNERPADDING", (0,0), (-1,-1), 8),
        ])
    ))
    story.append(Spacer(1, 14))

    # Footer
    story.append(Paragraph(f"© {created.strftime('%Y')} Nouvel — This document was generated electronically.", Meta))

    doc.build(story)
    return buf.getvalue()
