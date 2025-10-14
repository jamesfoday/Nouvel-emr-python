from __future__ import annotations

from datetime import date
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

from django.apps import apps
from django.db import transaction
from django.db.models import Q, QuerySet

from .models import Patient


# ---- Normalizers (kept) ----

def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str) -> str:
    raw = (value or "").strip()
    for ch in (" ", "-", "(", ")", "."):
        raw = raw.replace(ch, "")
    return raw


def parse_iso_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value) if value else None
    except Exception:
        return None


# ---- Duplicate search & scoring (kept) ----

def find_possible_duplicates(
    given_name: str = "",
    family_name: str = "",
    date_of_birth=None,
    email: str = "",
    phone: str = "",
) -> QuerySet[Patient]:
    """
    Search candidates by:
      - exact email OR exact phone (normalized), OR
      - exact (family + given + DOB).
    Only active (not merged) patients are returned.
    """
    email_n = normalize_email(email)
    phone_n = normalize_phone(phone)
    dob = parse_iso_date(date_of_birth)

    q = Q()
    if email_n:
        q |= Q(email__iexact=email_n)
    if phone_n:
        q |= Q(phone__iexact=phone_n)
    if family_name and given_name and dob:
        q |= (
            Q(family_name__iexact=family_name.strip())
            & Q(given_name__iexact=given_name.strip())
            & Q(date_of_birth=dob)
        )
    return Patient.objects.filter(q, is_active=True, merged_into__isnull=True).distinct()


def score_duplicate(candidate: Patient, *, email: str, phone: str, given_name: str, family_name: str, dob):
    """
    Basic score:
      +100 exact email, +100 exact phone, +70 exact (name + DOB).
    """
    score = 0
    if email and candidate.email and normalize_email(email) == normalize_email(candidate.email):
        score += 100
    if phone and candidate.phone and normalize_phone(phone) == normalize_phone(candidate.phone):
        score += 100
    if (
        parse_iso_date(dob) == candidate.date_of_birth
        and candidate.family_name.strip().lower() == (family_name or "").strip().lower()
        and candidate.given_name.strip().lower() == (given_name or "").strip().lower()
    ):
        score += 70
    return score


# ---- Merge service ----

@dataclass
class MergeResult:
    moved: Dict[str, int]
    notes: List[str]


# List of (app_label.ModelName, patient_field)
TARGETS: List[Tuple[str, str]] = [
    ("appointments.Appointment", "patient"),
    ("encounters.Encounter", "patient"),
    ("prescriptions.Prescription", "patient"),
    ("documents.Document", "patient"),
    
]


def _get_model(label: str):
    """Try apps.<label> first (project style), then plain app_label.Model."""
    try:
        return apps.get_model(f"apps.{label}")
    except Exception:
        try:
            return apps.get_model(label)
        except Exception:
            return None


@transaction.atomic
def merge_into(primary: Patient, other: Patient) -> MergeResult:
    """
    Reassign all patient-bound relations from 'other' to 'primary',
    then archive 'other' via Patient.mark_merged_into(primary).
    """
    if primary.pk == other.pk:
        raise ValueError("Cannot merge a patient into itself.")
    if other.merged_into_id:
        raise ValueError("The 'other' patient is already merged.")

    # Lock both rows to avoid race conditions (order by pk).
    ids = sorted([primary.pk, other.pk])
    Patient.objects.select_for_update().filter(pk__in=ids)

    moved: Dict[str, int] = {}
    notes: List[str] = []

    for label, field in TARGETS:
        Model = _get_model(label)
        if not Model:
            notes.append(f"Skip {label}: model not found")
            continue
        if not any(f.name == field for f in Model._meta.fields):
            notes.append(f"Skip {label}: field '{field}' missing")
            continue

        qs = Model.objects.filter(**{f"{field}_id": other.pk})
        count = qs.count()
        if count:
            qs.update(**{field: primary})
        moved[label] = count

    # Archive & point the other record
    other.mark_merged_into(primary)

    return MergeResult(moved=moved, notes=notes)
