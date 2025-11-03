# apps/patients/ui_views.py
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordResetForm
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
from django.urls import reverse
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
def _to_int(value, default: int, *, min_value: int = 1, max_value: int | None = 100) -> int:
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


def _unique_username_from_email_or_name(email: str, given: str, family: str) -> str:
    User = get_user_model()
    base = (email.split("@")[0] if email else "").strip() or slugify(f"{given}.{family}") or "user"
    candidate = base
    i = 1
    while User.objects.filter(username__iexact=candidate).exists():
        i += 1
        candidate = f"{base}{i}"
    return candidate


def _assign_patient_to_clinician(patient: Patient, clinician) -> None:
    """
    Link Patient -> Clinician using whatever relation you already have.
    Supports:
      1) FK patient.primary_clinician
      2) M2M patient.clinicians.add(user)
      3) Through models like PatientClinician / PatientAssignment
    """
    # FK
    if hasattr(patient, "primary_clinician_id"):
        patient.primary_clinician = clinician
        patient.save(update_fields=["primary_clinician"])
        return

    # M2M
    if hasattr(patient, "clinicians"):
        try:
            patient.clinicians.add(clinician)
            return
        except Exception:
            pass

    # Through model (heuristic)
    for app_label, model_name in [
        ("patients", "PatientClinician"),
        ("patients", "PatientAssignment"),
        ("clinicians", "PatientClinician"),
        ("clinicians", "PatientAssignment"),
    ]:
        try:
            Link = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        fields = {f.name for f in Link._meta.get_fields()}
        kwargs = {}
        if "patient" in fields:
            kwargs["patient"] = patient
        if "clinician" in fields:
            kwargs["clinician"] = clinician
        if kwargs:
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

    # Superuser always allowed
    if getattr(user, "is_superuser", False):
        return True

    # Explicit reception-type roles
    if has_role(user, "reception", "receptionist", "frontdesk"):
        return True

    # Fallback: any staff user
    return getattr(user, "is_staff", False)


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


# -------------------------
# Console / Global (existing)
# -------------------------
@login_required
def console_home(request: HttpRequest):
    return render(request, "console/console.html")


@login_required
def patients_home(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    highlight_id = _int_or_none(request.GET.get("highlight"))
    base = Patient.objects.filter(is_active=True, merged_into__isnull=True)
    if q:
        base = base.filter(_name_q(q.split()))
    initial = base.order_by("family_name", "given_name", "id")[:50]
    return render(
        request,
        "patients/console.html",
        {"initial_patients": initial, "q": q, "highlight_id": highlight_id},
    )


@login_required
def patients_search(request):
    q = (request.GET.get("q") or "").strip()
    template = request.GET.get("template", "table")
    limit = int(request.GET.get("limit") or 40)

    patients = Patient.objects.all()

    if q:
        patients = patients.filter(
            Q(family_name__icontains=q) |
            Q(given_name__icontains=q)  |
            Q(email__icontains=q)       |
            Q(phone__icontains=q)
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
        return render(request, "patients/_table.html", {**ctx, "q": q})


# -------------------------
# Patient create (global staff)
# -------------------------
@login_required
def patients_create(request: HttpRequest):
    """
    Create patient. If 'create_portal_account' is checked, ensure a User exists
    for the email and email a one-time Set Password link.
    Auto-generates an external_id like PT-000123.
    Template: templates/patients/create.html
    """
    if request.method == "POST":
        given_name  = (request.POST.get("given_name") or "").strip()
        family_name = (request.POST.get("family_name") or "").strip()
        email       = (request.POST.get("email") or "").strip().lower()
        phone       = (request.POST.get("phone") or "").strip()
        dob_raw     = (request.POST.get("date_of_birth") or "").strip()
        sex         = (request.POST.get("sex") or "").strip()
        address_line= (request.POST.get("address_line") or "").strip()
        city        = (request.POST.get("city") or "").strip()
        region      = (request.POST.get("region") or "").strip()
        postal_code = (request.POST.get("postal_code") or "").strip()
        country     = (request.POST.get("country") or "").strip()
        create_login= request.POST.get("create_portal_account") == "on"
        send_guide  = request.POST.get("send_credentials") == "on"

        errors = []
        if not given_name:
            errors.append("Given name is required.")
        if not family_name:
            errors.append("Family name is required.")
        if create_login and not email:
            errors.append("Email is required to create a portal account.")

        dob = None
        if dob_raw:
            try:
                dob = date.fromisoformat(dob_raw)
            except Exception:
                errors.append("Date of birth format should be YYYY-MM-DD.")

        if errors:
            messages.error(request, " ".join(errors))
            return render(request, "patients/create.html", {"form": request.POST})

        patient = Patient.objects.create(
            given_name=given_name,
            family_name=family_name,
            email=email or None,
            phone=phone,
            date_of_birth=dob,
            sex=sex,
            address_line=address_line,
            city=city,
            region=region,
            postal_code=postal_code,
            country=country,
            is_active=True,
        )

        # Generate human-readable ID after we have a PK
        try:
            if not getattr(patient, "external_id", None):
                patient.external_id = f"PT-{patient.pk:06d}"
                patient.save(update_fields=["external_id"])
        except Exception:
            pass

        sent_email = False
        if create_login and email:
            User = get_user_model()
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                username = _unique_username_from_email_or_name(email, given_name, family_name)
                user = User.objects.create(
                    username=username,
                    email=email,
                    is_active=True,
                )
                if hasattr(user, "first_name"):
                    user.first_name = given_name
                if hasattr(user, "last_name"):
                    user.last_name = family_name
                if hasattr(user, "is_staff"):
                    user.is_staff = False
                user.save()

            # Link Patient -> User if model has FK
            if hasattr(patient, "user_id") and not patient.user_id:
                try:
                    patient.user = user
                    patient.save(update_fields=["user"])
                except Exception:
                    pass

            # Send a Set-Password email using Django's password reset
            pr_form = PasswordResetForm({"email": email})
            if pr_form.is_valid():
                pr_form.save(
                    request=request,
                    use_https=request.is_secure(),
                    email_template_name="emails/set_password_email.txt",
                    subject_template_name="emails/set_password_subject.txt",
                    from_email=None,
                )
                sent_email = True

        if create_login and sent_email:
            messages.success(request, f"Patient created. We emailed {email} a secure link to set their password.")
        else:
            messages.success(request, "Patient created.")

        if send_guide and email:
            try:
                subject = "Welcome to Nouvel Portal"
                html_body = f"""
                  <p>Hi {given_name},</p>
                  <p>Your patient record was created. If a portal account was requested, check your email for a
                  one-time link to set your password. You can always sign in at <strong>/portal/</strong>.</p>
                  <p>— Nouvel Team</p>
                """
                msg = EmailMultiAlternatives(subject, strip_tags(html_body), to=[email])
                msg.attach_alternative(html_body, "text/html")
                msg.send(fail_silently=True)
            except Exception:
                pass

        q = email or phone or f"{patient.given_name} {patient.family_name}"
        params = urlencode({"q": q, "highlight": patient.pk})
        return redirect(f"{reverse('patients_ui:patients_home')}?{params}")

    return render(request, "patients/create.html")


# -------------------------
# Login link (existing; must build absolute URL for email)
# -------------------------
@login_required
def patients_login_link(request: HttpRequest, pk: int):
    if not (request.user.is_superuser or request.user.is_staff):
        return HttpResponseForbidden("Not allowed.")

    patient = get_object_or_404(Patient, pk=pk)
    email = (patient.email or "").strip().lower()
    if not email:
        return HttpResponseBadRequest("Patient has no email.")

    User = get_user_model()
    user, _created = User.objects.get_or_create(
        email=email,
        defaults={
            "username": _unique_username_from_email_or_name(email, patient.given_name, patient.family_name),
            "is_active": True,
        },
    )
    if getattr(user, "is_staff", False):
        return HttpResponseBadRequest("Email belongs to a staff account; cannot issue patient link.")

    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = PasswordResetTokenGenerator().make_token(user)
    path = reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
    link = request.build_absolute_uri(path)  # <-- intentionally absolute for email

    if hasattr(patient, "user_id") and not patient.user_id:
        try:
            patient.user = user
            patient.save(update_fields=["user"])
        except Exception:
            pass

    return JsonResponse({"link": link})


# -------------------------
# Merge (existing)
# -------------------------
@login_required
def merge_confirm(request: HttpRequest):
    primary_id = request.GET.get("primary")
    other_id = request.GET.get("other")
    if not (primary_id and other_id):
        return HttpResponseBadRequest("Missing ids")
    primary = get_object_or_404(Patient, pk=primary_id)
    other = get_object_or_404(Patient, pk=other_id)
    if not (other.is_active and other.merged_into_id is None):
        return HttpResponseBadRequest("Source patient is not mergeable.")
    return render(request, "patients/_merge_confirm.html", {"primary": primary, "other": other})


@login_required
def merge_execute(request: HttpRequest):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    primary_id = request.POST.get("primary_id")
    other_id = request.POST.get("other_id")
    if not (primary_id and other_id):
        return HttpResponseBadRequest("Missing ids")

    primary = get_object_or_404(Patient, pk=primary_id)
    other = get_object_or_404(Patient, pk=other_id)

    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Not allowed.")
        return redirect("patients_ui:patients_home")

    try:
        result = merge_into(primary, other)
        moved = ", ".join(f"{k.split('.')[-1]}={v}" for k, v in result.moved.items())
        messages.success(
            request,
            f"Merged “{other.full_name}” → “{primary.full_name}”. Moved: {moved or 'none'}."
        )
    except Exception as e:
        messages.error(request, f"Merge failed: {e}")
        return redirect("patients_ui:patients_home")

    try:
        return redirect("patients_ui:detail", pk=primary.pk)
    except Exception:
        return redirect("patients_ui:patients_home")


# -------------------------
# Detail / Edit / Deactivate (existing)
# -------------------------
@login_required
def patient_detail(request: HttpRequest, pk: int):
    patient = get_object_or_404(Patient, pk=pk)

    appts = encounters = docs = tests = rx = []
    try:
        from apps.appointments.models import Appointment
        appts = (
            Appointment.objects
            .filter(patient_id=pk)
            .select_related("clinician")
            .order_by("-start")[:50]
        )
    except Exception:
        pass
    try:
        from apps.encounters.models import Encounter
        encounters = (
            Encounter.objects
            .filter(patient_id=pk)
            .select_related("clinician")
            .order_by("-created_at")[:50]
        )
    except Exception:
        pass
    try:
        from apps.documents.models import Document
        docs = Document.objects.filter(patient_id=pk).order_by("-created_at")[:50]
        tests = Document.objects.filter(
            patient_id=pk, kind__in=["lab_result", "test_result"]
        ).order_by("-created_at")[:25]
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
        {"p": patient, "appts": appts, "encounters": encounters, "docs": docs, "tests": tests, "rx": rx},
    )


@login_required
def patients_edit(request: HttpRequest, pk: int):
    p = get_object_or_404(Patient, pk=pk)

    if request.method == "POST":
        fields = [
            "given_name","family_name","email","phone","sex",
            "address_line","city","region","postal_code","country",
        ]
        for f in fields:
            setattr(p, f, (request.POST.get(f) or "").strip())

        dob_raw = (request.POST.get("date_of_birth") or "").strip()
        if dob_raw:
            try:
                p.date_of_birth = date.fromisoformat(dob_raw)
            except Exception:
                messages.error(request, "Date of birth must be YYYY-MM-DD.")
                return render(request, "patients/edit.html", {"p": p, "form": request.POST})

        p.save()
        messages.success(request, "Patient updated.")
        return redirect("patients_ui:detail", pk=p.pk)

    return render(request, "patients/edit.html", {"p": p})


@login_required
def patients_deactivate(request: HttpRequest, pk: int):
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    if not (request.user.is_superuser or request.user.is_staff):
        messages.error(request, "Not allowed.")
        return redirect("patients_ui:detail", pk=pk)

    p = get_object_or_404(Patient, pk=pk)
    p.is_active = False
    p.save(update_fields=["is_active"])
    messages.success(request, "Patient deactivated.")
    return redirect("patients_ui:patients_home")


# -------------------------
# Pick list (existing)
# -------------------------
@login_required
def pick_list(request: HttpRequest):
    q = (request.GET.get("q") or "").strip()
    base = Patient.objects.filter(is_active=True, merged_into__isnull=True)
    if q:
        base = base.filter(_name_q(q.split()))
    rows = base.order_by("family_name", "given_name", "id")[:50]
    return render(request, "patients/_pick_list.html", {"patients": rows})


# ======================================================================
# RECEPTION: see-all + create-and-assign + activate/deactivate + HTMX
# ======================================================================
@login_required
def reception_patients_list(request: HttpRequest):
    """
    Reception can see all patients assigned to clinicians (or all, if no direct link exists).
    HTMX: returns rows partial when HX-Request.
    NOTE: uses only relative paths (reverse / {% url %}) — no absolute URLs here.
    """
    if not _require_reception(request):
        messages.error(request, "Not allowed.")
        return redirect("patients_ui:patients_home")

    q = (request.GET.get("q") or "").strip()
    base = Patient.objects.all()

    # Prefer “patients assigned to any clinician”
    if hasattr(Patient, "primary_clinician_id"):
        base = base.filter(primary_clinician__isnull=False)
    elif hasattr(Patient, "clinicians"):
        base = base.filter(clinicians__isnull=False).distinct()

    if q:
        base = base.filter(
            Q(family_name__icontains=q) |
            Q(given_name__icontains=q)  |
            Q(email__icontains=q)       |
            Q(phone__icontains=q)
        )

    patients = base.order_by("family_name", "given_name", "id")[:200]
    ctx = {"patients": patients, "q": q}

    # HTMX partial for tbody updates
    if _is_htmx(request):
        if request.GET.get("view") == "cards":
            return TemplateResponse(request, "reception/_patients_cards.html", ctx)
        return TemplateResponse(request, "reception/_patients_rows.html", ctx)

    return render(request, "reception/patients_list.html", ctx)


@login_required
def reception_patient_toggle_active(request: HttpRequest, pk: int):
    """
    Toggle is_active for a patient and return the updated row partial.
    HTMX: swaps the single row in the table.
    """
    if not _require_reception(request):
        return HttpResponseBadRequest("Not allowed")
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    p = get_object_or_404(Patient, pk=pk)
    p.is_active = not p.is_active
    p.save(update_fields=["is_active"])

    # Return just the row HTML so HTMX can swap it in place
    return TemplateResponse(request, "reception/_patients_row.html", {"p": p})


@login_required
def reception_patient_create(request: HttpRequest):
    """
    Reception creates a patient and MUST choose a clinician to assign.
    On save, the patient is wired to the clinician and will appear in the clinician’s list.
    """
    if not _require_reception(request):
        messages.error(request, "Not allowed.")
        return redirect("home")

    User = get_user_model()

    if request.method == "POST":
        given_name  = (request.POST.get("given_name") or "").strip()
        family_name = (request.POST.get("family_name") or "").strip()
        email       = (request.POST.get("email") or "").strip().lower() or None
        phone       = (request.POST.get("phone") or "").strip()
        dob_raw     = (request.POST.get("date_of_birth") or "").strip()
        sex         = (request.POST.get("sex") or "").strip() or None
        address_line= (request.POST.get("address_line") or "").strip() or None
        city        = (request.POST.get("city") or "").strip() or None
        region      = (request.POST.get("region") or "").strip() or None
        postal_code = (request.POST.get("postal_code") or "").strip() or None
        country     = (request.POST.get("country") or "").strip() or None
        clinician_id= (request.POST.get("clinician_id") or "").strip()

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
                clinician = User.objects.get(pk=int(clinician_id), is_active=True, is_staff=True)
            except (User.DoesNotExist, ValueError):
                errors.append("Selected clinician is invalid.")

        if errors:
            messages.error(request, " ".join(errors))
            clinicians = User.objects.filter(is_staff=True, is_active=True).order_by("first_name", "last_name", "id")
            return render(request, "reception/patient_create.html", {"clinicians": clinicians, "form": request.POST})

        patient = Patient.objects.create(
            given_name=given_name,
            family_name=family_name,
            email=email,
            phone=phone,
            date_of_birth=dob,
            sex=sex,
            address_line=address_line,
            city=city,
            region=region,
            postal_code=postal_code,
            country=country,
            is_active=True,
        )

        # Human-readable external ID
        try:
            if not getattr(patient, "external_id", None):
                patient.external_id = f"PT-{patient.pk:06d}"
                patient.save(update_fields=["external_id"])
        except Exception:
            pass

        # Wire to clinician
        if clinician:
            _assign_patient_to_clinician(patient, clinician)

        messages.success(request, "Patient created and assigned to clinician.")
        return redirect("patients_ui:reception_patients_list")

    clinicians = User.objects.filter(is_staff=True, is_active=True).order_by("first_name", "last_name", "id")
    return render(request, "reception/patient_create.html", {"clinicians": clinicians})


@login_required
def reception_patient_activate(request: HttpRequest, pk: int):
    if not _require_reception(request):
        messages.error(request, "Not allowed.")
        return redirect("home")
    if request.method != "POST":
        return HttpResponseBadRequest("POST only")

    p = get_object_or_404(Patient, pk=pk)
    p.is_active = True
    # Clear merge flags if present
    if hasattr(p, "merged_into_id"):
        p.merged_into_id = None
    if hasattr(p, "merged_at"):
        p.merged_at = None
    p.save()
    messages.success(request, "Patient reactivated.")
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