# apps/patients/ui_views.py
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q, Value, CharField, F
from django.db.models.functions import Concat, Coalesce, Trim
from django.http import (
    HttpRequest,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse, NoReverseMatch
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify
from django.apps import apps

from .models import Patient
from .services import merge_into

# RBAC helpers (plain-Django)
from apps.rbac.utils import has_role


# -------------------------
# Internal helpers
# -------------------------


def _build_portal_login_link(request: HttpRequest, user) -> str | None:
    """
    Build an absolute URL to a password-reset / set-password page for this user.

    It tries, in order:
      1. portal_ui:invite_accept                (if you have a custom invite flow)
      2. portal_ui:password_reset_confirm       (patient portal-style reset)
      3. password_reset_confirm                 (Django contrib.auth default)
    Returns:
        URL string on success, or None if no matching URL name exists.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = portal_token_generator.make_token(user)

    candidates = [
        ("portal_ui:invite_accept", {"uidb64": uid, "token": token}),
        ("portal_ui:password_reset_confirm", {"uidb64": uid, "token": token}),
        ("password_reset_confirm", {"uidb64": uid, "token": token}),
    ]

    for name, kwargs in candidates:
        try:
            path = reverse(name, kwargs=kwargs)
            return request.build_absolute_uri(path)
        except NoReverseMatch:
            continue

    # None of the expected URL names exist – caller will handle this as an error.
    return None


def _to_int(
    value,
    default: int,
    *,
    min_value: int = 1,
    max_value: int | None = 100,
) -> int:
    try:
        i = int(value)
    except (TypeError, ValueError):
        return default
    if i < min_value:
        return default
    if max_value is not None and i > max_value:
        i = max_value
    return i


def _int_or_none(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _name_q(terms: list[str]) -> Q:
    cond = Q()
    for t in terms:
        cond &= (
            Q(family_name__icontains=t)
            | Q(given_name__icontains=t)
            | Q(email__icontains=t)
            | Q(phone__icontains=t)
            | Q(external_id__icontains=t)
        )
    return cond


def _unique_username_from_email_or_name(
    email: str,
    given: str,
    family: str,
) -> str:
    User = get_user_model()
    base = (
        (email.split("@")[0] if email else "").strip()
        or slugify(f"{given}.{family}")
        or "user"
    )
    candidate = base
    i = 1
    while User.objects.filter(username__iexact=candidate).exists():
        i += 1
        candidate = f"{base}{i}"
    return candidate


def _assign_patient_to_clinician(patient: Patient, clinician) -> None:
    """
    Safely assign a patient to a clinician.

    - If the Patient model has a `primary_clinician` field, set it if empty.
    - If the Patient model has a `clinicians` M2M field, add the clinician there too.
    """

    # Handle FK/field `primary_clinician` if present
    if hasattr(patient, "primary_clinician"):
        try:
            current = patient.primary_clinician
        except Exception:
            # Covers cases like reverse one-to-one RelatedObjectDoesNotExist
            current = None

        if not current:
            try:
                patient.primary_clinician = clinician
                patient.save(update_fields=["primary_clinician"])
            except Exception:
                # If update_fields fails (e.g. field name mismatch), fall back to full save
                try:
                    patient.primary_clinician = clinician
                    patient.save()
                except Exception:
                    # As a last resort, just ignore instead of 500-ing
                    pass

    # If you also have an M2M `clinicians` field, add the clinician there
    if hasattr(patient, "clinicians"):
        try:
            patient.clinicians.add(clinician)
        except Exception:
            # If it's not actually a M2M or something else goes wrong, avoid crashing
            pass



def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def _wants_json(request: HttpRequest) -> bool:
    """
    Detect if this is an AJAX/HTMX/XHR-style call that expects a non-HTML response.
    We want this to be TRUE for the patient list "Login link" button.
    """
    # HTMX
    if request.headers.get("HX-Request") == "true":
        return True

    # Classic XHR / many JS libs
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True

    # Fetch with explicit JSON accept
    accept = request.headers.get("Accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return True

    # Many fetch() calls send "text/html,*/*" - treat non-HTML-only as JSON-ish
    if "text/html" not in accept:
        return True

    return False


# -------------------------
# Portal: password reset helpers
# -------------------------


class PortalPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        login_timestamp = (
            ""
            if user.last_login is None
            else user.last_login.replace(microsecond=0, tzinfo=None)
        )
        return f"{user.pk}{user.is_active}{login_timestamp}{timestamp}"


portal_token_generator = PortalPasswordResetTokenGenerator()


def _send_portal_password_reset_email(
    request: HttpRequest,
    user,
    email: str,
) -> bool:
    """
    Send a patient-portal password reset email.

    Returns:
        True  -> email send path completed without raising.
        False -> any error (missing URL, template, email backend, etc.).
    """
    try:
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = portal_token_generator.make_token(user)

        try:
            path = reverse(
                "portal_ui:password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
        except NoReverseMatch:
            # Portal URLs not wired yet – treat as failure but don't crash.
            return False

        reset_url = request.build_absolute_uri(path)

        subject = "Reset your Nouvel patient portal password"
        html_body = render(
            request,
            "portal/emails/password_reset.html",
            {
                "reset_url": reset_url,
                "user": user,
            },
        ).content.decode("utf-8")
        text_body = strip_tags(html_body)

        msg = EmailMultiAlternatives(
            subject,
            text_body,
            settings.DEFAULT_FROM_EMAIL,
            [email],
        )
        msg.attach_alternative(html_body, "text/html")

        # Any SMTP / backend issue will be caught by outer try/except.
        msg.send(fail_silently=False)
        return True
    except Exception:
        # In DEBUG this will still show in console logs, but won't crash the view.
        return False


def _send_portal_invite_email(request: HttpRequest, user, email: str):
    """
    Send a patient portal invite email with a one-time set-password link.

    Tries portal_ui:invite_accept first.
    If that URL doesn't exist yet, falls back to portal_ui:password_reset_confirm.
    If neither exists, this becomes a no-op (no crash).
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = portal_token_generator.make_token(user)

    # Try invite_accept first, then fallback to password_reset_confirm
    try:
        path = reverse(
            "portal_ui:invite_accept",
            kwargs={"uidb64": uid, "token": token},
        )
    except NoReverseMatch:
        try:
            path = reverse(
                "portal_ui:password_reset_confirm",
                kwargs={"uidb64": uid, "token": token},
            )
        except NoReverseMatch:
            # No suitable URL configured yet – skip sending invite instead of crashing
            return

    invite_url = request.build_absolute_uri(path)

    subject = "Access your Nouvel patient portal"
    html_body = render(
        request,
        "portal/emails/invite.html",
        {
            "invite_url": invite_url,
            "user": user,
        },
    ).content.decode("utf-8")
    text_body = strip_tags(html_body)

    msg = EmailMultiAlternatives(
        subject,
        text_body,
        settings.DEFAULT_FROM_EMAIL,
        [email],
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)


# -------------------------
# Link model (optional)
# -------------------------
try:
    Link = apps.get_model("core", "Link")
except LookupError:
    Link = None


def _ensure_patient_links(patient: Patient):
    """
    Ensure we have stable links for:
      - portal_home
      - portal_appointments
      - portal_tests
      - portal_documents

    If there is no core.Link model, this is a no-op.
    """
    if Link is None:
        return

    mapping = {
        "portal_home": reverse("portal_ui:home"),
        "portal_appointments": reverse("portal_ui:appointments"),
        "portal_tests": reverse("portal_ui:tests"),
        "portal_documents": reverse("portal_ui:documents"),
    }

    for key, url in mapping.items():
        Link.objects.get_or_create(
            kind="patient-portal",
            slug=key,
            defaults={"url": url},
        )


def _ensure_patient_specific_links(patient: Patient):
    """
    Ensure we have links bound to this specific patient (if needed).

    If there is no Link model or it doesn’t have a patient FK, this is a no-op.
    """
    if Link is None:
        return

    if not hasattr(Link, "patient"):
        return

    mapping = {
        "portal_patient_home": reverse("portal_ui:home"),
    }

    for key, url in mapping.items():
        kwargs = {
            "kind": "patient-portal",
            "slug": key,
            "url": url,
            "patient": patient,
        }
        if hasattr(Link, "clinician") and getattr(
            patient,
            "primary_clinician",
            None,
        ):
            kwargs["clinician"] = patient.primary_clinician
        Link.objects.get_or_create(**kwargs)
        return


def _require_reception(request) -> bool:
    """
    Reception access gate:
      - superuser: always allowed
      - has ANY of roles: reception, receptionist, frontdesk
      - OR is_staff (fallback)
    """
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if has_role(user, "reception", "receptionist", "frontdesk"):
        return True

    return getattr(user, "is_staff", False)


def _require_console_access(user) -> bool:
    """
    Console access gate for patient records and console pages.

    Allowed:
      - superuser
      - is_staff
      - RBAC roles: reception / receptionist / frontdesk / clinician / clinicians

    Patients (role "patient") should NOT have console access.
    """
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    if getattr(user, "is_staff", False):
        return True

    if has_role(
        user,
        "reception",
        "receptionist",
        "frontdesk",
        "clinician",
        "clinicians",
    ):
        return True

    return False


# -------------------------
# Console / Global
# -------------------------


@login_required
def console_home(request: HttpRequest):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")
    return render(request, "console/console.html")


@login_required
def patients_home(request: HttpRequest):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")
    q = (request.GET.get("q") or "").strip()
    highlight_id = _int_or_none(request.GET.get("highlight"))
    base = Patient.objects.filter(is_active=True, merged_into__isnull=True)
    if q:
        base = base.filter(_name_q(q.split()))
    initial = base.order_by("family_name", "given_name", "id")[:50]
    return render(
        request,
        "patients/console.html",
        {
            "initial_patients": initial,
            "q": q,
            "highlight_id": highlight_id,
        },
    )


@login_required
def patients_search(request: HttpRequest):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")
    q = (request.GET.get("q") or "").strip()
    template = request.GET.get("template", "table")
    limit = int(request.GET.get("limit") or 40)

    patients = Patient.objects.all()

    if q:
        patients = patients.filter(
            Q(family_name__icontains=q)
            | Q(given_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
        )

    fam = Coalesce(F("family_name"), Value(""))
    giv = Coalesce(F("given_name"), Value(""))
    comma = Value(", ")

    patients = patients.annotate(
        label=Trim(
            Coalesce(
                Concat(fam, comma, giv, output_field=CharField()),
                Concat(fam, giv, output_field=CharField()),
                output_field=CharField(),
            )
        )
    ).order_by("family_name", "given_name")[:limit]

    ctx = {"patients": patients}

    if template == "dm":
        return render(request, "patients/_dm_search_list.html", ctx)
    else:
        return render(request, "patients/_search_table.html", ctx)


# -------------------------
# Create / Edit patient (console)
# -------------------------


@login_required
def patients_create(request: HttpRequest):
    """
    Create patient. If 'create_portal_account' is checked, ensure a User exists
    for the email and email a one-time Set Password or invite link.
    Auto-generates an external_id like PT-000123.
    """
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    if request.method == "POST":
        given_name = (request.POST.get("given_name") or "").strip()
        family_name = (request.POST.get("family_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        dob_raw = (request.POST.get("date_of_birth") or "").strip()
        sex = (request.POST.get("sex") or "").strip()
        sex = sex or ""  # make sure never None
        address_line = (request.POST.get("address_line") or "").strip()
        city = (request.POST.get("city") or "").strip()
        region = (request.POST.get("region") or "").strip()
        postal_code = (request.POST.get("postal_code") or "").strip()
        country = (request.POST.get("country") or "").strip()
        create_portal_account = request.POST.get("create_portal_account") == "on"

        errors = []
        if not given_name:
            errors.append("Given name is required.")
        if not family_name:
            errors.append("Family name is required.")

        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
            except Exception:
                errors.append("Date of birth format should be YYYY-MM-DD.")

        if errors:
            messages.error(request, " ".join(errors))
            return render(
                request,
                "patients/create.html",
                {"form": request.POST},
            )

        # IMPORTANT: external_id cannot be NULL at DB level, so give a placeholder
        patient = Patient.objects.create(
            given_name=given_name,
            family_name=family_name,
            email=email or None,
            phone=phone,
            date_of_birth=dob,
            sex=sex or "",
            address_line=address_line,
            city=city,
            region=region,
            postal_code=postal_code,
            country=country,
            external_id="",  # placeholder; will be overwritten below
            is_active=True,
        )

        # Generate human-readable ID after we have a PK
        try:
            if not getattr(patient, "external_id", None):
                patient.external_id = f"PT-{patient.pk:06d}"
                patient.save(update_fields=["external_id"])
        except Exception:
            pass

        _ensure_patient_links(patient)
        _ensure_patient_specific_links(patient)

        if create_portal_account and email:
            User = get_user_model()
            user, created = User.objects.get_or_create(
                email=email,
                defaults={
                    "username": _unique_username_from_email_or_name(
                        email,
                        given_name,
                        family_name,
                    ),
                    "is_active": True,
                },
            )
            if created:
                # Brand new user → send invite email
                _send_portal_invite_email(request, user, email)
            else:
                # Existing user:
                # 1) Link Patient -> User if model has FK
                if hasattr(patient, "user_id") and not patient.user_id:
                    try:
                        patient.user = user
                        patient.save(update_fields=["user"])
                    except Exception:
                        pass

                # 2) Send portal-style password reset email
                try:
                    _send_portal_password_reset_email(request, user, email)
                except Exception:
                    # Don't crash on email issues in dev
                    pass

        q = email or phone or f"{patient.given_name} {patient.family_name}"
        params = urlencode({"q": q, "highlight": patient.pk})
        return redirect(f"{reverse('patients_ui:patients_home')}?{params}")

    return render(request, "patients/create.html")


# -------------------------
# Login link (console)
# -------------------------


@login_required
def patients_login_link(request: HttpRequest, pk: int):
    """
    Generate a portal login URL for this patient.

    - If called via JS (X-Requested-With: XMLHttpRequest), returns JSON:
        { "ok": true, "link": "https://..." }
      with HTTP 200 on success, 4xx on failure.

    - If called normally (from detail page), redirects back with flash messages.
    """
    wants_json = _wants_json(request)

    try:
        # RBAC gate
        if not _require_console_access(request.user):
            if wants_json:
                return JsonResponse(
                    {"ok": False, "error": "Not allowed."},
                    status=403,
                )
            return HttpResponseForbidden("Not allowed.")

        patient = get_object_or_404(Patient, pk=pk)

        email = (patient.email or "").strip().lower()
        if not email:
            msg = "This patient does not have an email address on file."
            if wants_json:
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect("patients_ui:detail", pk=pk)

        # Ensure a user exists for this email
        User = get_user_model()
        user, _created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": _unique_username_from_email_or_name(
                    email,
                    patient.given_name or "",
                    patient.family_name or "",
                ),
                "is_active": True,
            },
        )

        link = _build_portal_login_link(request, user)

        if not link:
            msg = (
                "Portal login link could not be generated. "
                "Check portal URLs configuration."
            )
            if wants_json:
                return JsonResponse({"ok": False, "error": msg}, status=400)
            messages.error(request, msg)
            return redirect("patients_ui:detail", pk=pk)

        # SUCCESS PATH
        if wants_json:
            # What the JS on console.html/list.html expects
            return JsonResponse({"ok": True, "link": link}, status=200)

        messages.success(request, "Portal login link generated.")
        # Optionally you could also send the email here using your email helper.
        return redirect("patients_ui:detail", pk=pk)

    except Exception:
        # Last-resort guard: never let this view 500.
        msg = (
            "Could not generate login link. Ensure the patient has an email "
            "and portal is configured."
        )
        if wants_json:
            return JsonResponse({"ok": False, "error": msg}, status=400)
        messages.error(request, msg)
        return redirect("patients_ui:detail", pk=pk)


# -------------------------
# Merge (console)
# -------------------------


@login_required
def merge_confirm(request: HttpRequest):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    primary_id = _int_or_none(request.GET.get("primary"))
    other_id = _int_or_none(request.GET.get("other"))

    if not primary_id or not other_id or primary_id == other_id:
        return HttpResponseBadRequest("Invalid merge parameters.")

    primary = get_object_or_404(Patient, pk=primary_id)
    other = get_object_or_404(Patient, pk=other_id)

    context = {
        "primary": primary,
        "other": other,
    }
    return render(request, "patients/merge_confirm.html", context)


@login_required
def merge_execute(request: HttpRequest):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    if request.method != "POST":
        return HttpResponseBadRequest("POST required.")

    primary_id = _int_or_none(request.POST.get("primary"))
    other_id = _int_or_none(request.POST.get("other"))

    if not primary_id or not other_id or primary_id == other_id:
        return HttpResponseBadRequest("Invalid merge parameters.")

    primary = get_object_or_404(Patient, pk=primary_id)
    other = get_object_or_404(Patient, pk=other_id)

    merge_into(primary, other)

    messages.success(request, "Patients merged successfully.")
    return redirect("patients_ui:detail", pk=primary.pk)


# -------------------------
# Detail / edit / deactivate (console)
# -------------------------


@login_required
def patient_detail(request: HttpRequest, pk: int):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    patient = get_object_or_404(Patient, pk=pk)
    _ensure_patient_links(patient)
    _ensure_patient_specific_links(patient)

    appts = encounters = docs = tests = rx = []
    try:
        from apps.appointments.models import Appointment

        appts = (
            Appointment.objects.filter(patient_id=pk)
            .select_related("clinician")
            .order_by("-start")[:50]
        )
    except Exception:
        pass
    try:
        from apps.encounters.models import Encounter

        encounters = (
            Encounter.objects.filter(patient_id=pk)
            .select_related("clinician")
            .order_by("-created_at")[:50]
        )
    except Exception:
        pass
    try:
        from apps.documents.models import Document

        docs = Document.objects.filter(patient_id=pk).order_by("-created_at")[:50]
        tests = (
            Document.objects.filter(
                patient_id=pk,
                kind__in=["lab_result", "test_result"],
            )
            .order_by("-created_at")[:25]
        )
    except Exception:
        pass
    try:
        from apps.prescriptions.models import Prescription

        rx = Prescription.objects.filter(patient_id=pk).order_by("-created_at")[:50]
    except Exception:
        pass

    return render(
        request,
        "patients/detail.html",
        {
            "p": patient,
            "patient": patient,
            "appts": appts,
            "encounters": encounters,
            "docs": docs,
            "tests": tests,
            "rx": rx,
        },
    )


@login_required
def patients_edit(request: HttpRequest, pk: int):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    patient = get_object_or_404(Patient, pk=pk)

    if request.method == "POST":
        given_name = (request.POST.get("given_name") or "").strip()
        family_name = (request.POST.get("family_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower()
        phone = (request.POST.get("phone") or "").strip()
        dob_raw = (request.POST.get("date_of_birth") or "").strip()
        sex = (request.POST.get("sex") or "").strip()
        sex = sex or ""  # ensure never None
        address_line = (request.POST.get("address_line") or "").strip()
        city = (request.POST.get("city") or "").strip()
        region = (request.POST.get("region") or "").strip()
        postal_code = (request.POST.get("postal_code") or "").strip()
        country = (request.POST.get("country") or "").strip()

        errors = []
        if not given_name:
            errors.append("Given name is required.")
        if not family_name:
            errors.append("Family name is required.")

        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
            except Exception:
                errors.append("Date of birth format should be YYYY-MM-DD.")

        if errors:
            messages.error(request, " ".join(errors))
            return render(
                request,
                "patients/edit.html",
                {"patient": patient, "p": patient, "form": request.POST},
            )

        patient.given_name = given_name
        patient.family_name = family_name
        patient.email = email or None
        patient.phone = phone or None
        patient.date_of_birth = dob
        patient.sex = sex or ""
        # defensive: fix legacy NULL values
        if patient.sex is None:
            patient.sex = ""
        patient.address_line = address_line or None
        patient.city = city or None
        patient.region = region or None
        patient.postal_code = postal_code or None
        patient.country = country or None
        patient.save()
        messages.success(request, "Patient updated successfully.")
        return redirect("patients_ui:detail", pk=patient.pk)

    return render(
        request,
        "patients/edit.html",
        {"patient": patient, "p": patient},
    )


@login_required
def patients_deactivate(request: HttpRequest, pk: int):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    patient = get_object_or_404(Patient, pk=pk)
    if request.method == "POST":
        patient.is_active = False
        patient.save(update_fields=["is_active"])
        messages.success(request, "Patient deactivated.")
        return redirect("patients_ui:patients_home")
    return render(request, "patients/deactivate.html", {"patient": patient})


# -------------------------
# Reception views (RBAC via _require_reception)
# -------------------------


@login_required
def reception_patients_list(request: HttpRequest):
    if not _require_reception(request):
        return HttpResponseForbidden("Not allowed.")

    q = (request.GET.get("q") or "").strip()
    base = Patient.objects.filter(is_active=True, merged_into__isnull=True)
    if q:
        base = base.filter(_name_q(q.split()))

    patients = base.order_by("family_name", "given_name", "id")[:200]
    ctx = {"patients": patients, "q": q}

    if _is_htmx(request):
        if request.GET.get("view") == "cards":
            return TemplateResponse(
                request,
                "reception/_patients_cards.html",
                ctx,
            )
        return TemplateResponse(request, "reception/_patients_rows.html", ctx)

    return render(request, "reception/patients_list.html", ctx)


@login_required
def reception_patient_toggle_active(request: HttpRequest, pk: int):
    if not _require_reception(request):
        return HttpResponseBadRequest("Not allowed")
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    p = get_object_or_404(Patient, pk=pk)
    p.is_active = not p.is_active
    p.save(update_fields=["is_active"])

    base = Patient.objects.filter(is_active=True, merged_into__isnull=True)
    patients = base.order_by("family_name", "given_name", "id")[:200]
    ctx = {"patients": patients, "q": ""}

    if _is_htmx(request):
        return TemplateResponse(request, "reception/_patients_rows.html", ctx)

    return redirect("patients_ui:reception_patients_list")


@login_required
def reception_patient_create(request: HttpRequest):
    """
    Reception creates a patient and MUST choose a clinician to assign.
    """
    if not _require_reception(request):
        messages.error(request, "Not allowed.")
        return redirect("home")

    User = get_user_model()

    if request.method == "POST":
        given_name = (request.POST.get("given_name") or "").strip()
        family_name = (request.POST.get("family_name") or "").strip()
        email = (request.POST.get("email") or "").strip().lower() or None
        phone = (request.POST.get("phone") or "").strip()
        dob_raw = (request.POST.get("date_of_birth") or "").strip()
        sex = (request.POST.get("sex") or "").strip()
        sex = sex or ""  # never None
        address_line = (request.POST.get("address_line") or "").strip() or None
        city = (request.POST.get("city") or "").strip() or None
        region = (request.POST.get("region") or "").strip() or None
        postal_code = (request.POST.get("postal_code") or "").strip() or None
        country = (request.POST.get("country") or "").strip() or None
        clinician_id = (request.POST.get("clinician_id") or "").strip()

        errors = []
        if not given_name:
            errors.append("Given name is required.")
        if not family_name:
            errors.append("Family name is required.")
        if not clinician_id:
            errors.append("Clinician selection is required for reception.")

        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
            except Exception:
                errors.append("Date of birth format should be YYYY-MM-DD.")

        clinician = None
        if clinician_id:
            try:
                clinician = User.objects.get(
                    pk=int(clinician_id),
                    is_active=True,
                    is_staff=True,
                )
            except (User.DoesNotExist, ValueError):
                errors.append("Selected clinician is invalid.")

        if errors:
            messages.error(request, " ".join(errors))
            clinicians = User.objects.filter(
                is_staff=True,
                is_active=True,
            ).order_by("first_name", "last_name", "id")
            return render(
                request,
                "reception/patient_create.html",
                {"clinicians": clinicians, "form": request.POST},
            )

        # IMPORTANT: external_id placeholder for NOT NULL column
        patient = Patient.objects.create(
            given_name=given_name,
            family_name=family_name,
            email=email,
            phone=phone,
            date_of_birth=dob,
            sex=sex or "",
            address_line=address_line,
            city=city,
            region=region,
            postal_code=postal_code,
            country=country,
            external_id="",  # placeholder
            is_active=True,
        )

        # Human-readable external ID
        try:
            if not getattr(patient, "external_id", None):
                patient.external_id = f"PT-{patient.pk:06d}"
                patient.save(update_fields=["external_id"])
        except Exception:
            pass

        if clinician:
            _assign_patient_to_clinician(patient, clinician)

        messages.success(request, "Patient created and assigned to clinician.")
        return redirect("patients_ui:reception_patients_list")

    clinicians = User.objects.filter(
        is_staff=True,
        is_active=True,
    ).order_by("first_name", "last_name", "id")
    return render(
        request,
        "reception/patient_create.html",
        {"clinicians": clinicians},
    )


@login_required
def reception_patient_activate(request: HttpRequest, pk: int):
    if not _require_reception(request):
        messages.error(request, "Not allowed.")
        return redirect("home")
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    p = get_object_or_404(Patient, pk=pk)
    p.is_active = True
    p.save(update_fields=["is_active"])
    messages.success(request, "Patient activated.")
    return redirect("patients_ui:reception_patients_list")


@login_required
def reception_patient_deactivate(request: HttpRequest, pk: int):
    if not _require_reception(request):
        messages.error(request, "Not allowed.")
        return redirect("home")
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    p = get_object_or_404(Patient, pk=pk)
    p.is_active = False
    p.save(update_fields=["is_active"])
    messages.success(request, "Patient deactivated.")
    return redirect("patients_ui:reception_patients_list")


# -------------------------
# Generic patient pick list (console)
# -------------------------


@login_required
def pick_list(request: HttpRequest):
    if not _require_console_access(request.user):
        return HttpResponseForbidden("Not allowed.")

    q = (request.GET.get("q") or "").strip()
    limit = _to_int(request.GET.get("limit"), default=20, min_value=1, max_value=100)
    highlight_id = _int_or_none(request.GET.get("highlight"))

    patients = Patient.objects.filter(is_active=True, merged_into__isnull=True)
    if q:
        patients = patients.filter(_name_q(q.split()))

    patients = patients.order_by("family_name", "given_name", "id")[:limit]

    return render(
        request,
        "patients/_pick_list.html",
        {
            "patients": patients,
            "highlight_id": highlight_id,
        },
    )
