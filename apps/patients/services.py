from datetime import date
from typing import Optional
from django.db.models import Q, QuerySet
from .models import Patient


# ---- Normalizers (I keep it simple for now; can swap to phonenumbers later) ----

def normalize_email(value: str) -> str:
    # I lowercase and strip whitespace to catch obvious duplicates.
    return (value or "").strip().lower()


def normalize_phone(value: str) -> str:
    # I remove spaces and common separators; real-world: use 'phonenumbers' lib.
    raw = (value or "").strip()
    for ch in (" ", "-", "(", ")", "."):
        raw = raw.replace(ch, "")
    return raw


def parse_iso_date(value) -> Optional[date]:
    # I accept either a date instance or 'YYYY-MM-DD' string.
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value) if value else None
    except Exception:
        return None


# ---- Duplicate search & scoring ----

def find_possible_duplicates(
    given_name: str = "",
    family_name: str = "",
    date_of_birth=None,
    email: str = "",
    phone: str = "",
) -> QuerySet[Patient]:
    """
    I search candidates by:
      - exact email OR exact phone (normalized), OR
      - exact (family + given + DOB).
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
    return Patient.objects.filter(q).distinct()


def score_duplicate(candidate: Patient, *, email: str, phone: str, given_name: str, family_name: str, dob):
    """
    I produce a basic score:
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
