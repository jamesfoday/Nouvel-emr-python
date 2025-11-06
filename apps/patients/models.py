from __future__ import annotations

from datetime import date
from typing import Optional

from django.db import models
from django.db.models import Q, F
from django.utils import timezone


# ------------ QuerySet / Manager helpers ------------ #

class PatientQuerySet(models.QuerySet):
    def active(self) -> "PatientQuerySet":
        return self.filter(is_active=True, merged_into__isnull=True)

    def inactive(self) -> "PatientQuerySet":
        return self.filter(is_active=False)

    def merged(self) -> "PatientQuerySet":
        return self.filter(merged_into__isnull=False)

    def name_search(self, text: str) -> "PatientQuerySet":
        """
        Pragmatic multi-term search across name/phone/email/external_id.
        Usage: Patient.objects.active().name_search("jhn smth")
        """
        text = (text or "").strip()
        if not text:
            return self
        terms = text.split()
        cond = Q()
        for t in terms:
            cond &= (
                Q(given_name__icontains=t)
                | Q(family_name__icontains=t)
                | Q(phone__icontains=t)
                | Q(email__icontains=t)
                | Q(external_id__icontains=t)
            )
        return self.filter(cond)


class PatientManager(models.Manager.from_queryset(PatientQuerySet)):  # type: ignore[misc]
    pass


# -------------------------- Model -------------------------- #

class Patient(models.Model):
    # --- Core demographics (intake & search) ---
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True, default="")  # free text for now

    # --- Contact identifiers (normalize in service layer) ---
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    external_id = models.CharField(max_length=64, blank=True, default="")  # e.g., MRN from another system

    # --- Lightweight address bundle ---
    address_line = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")

    # --- Merge / archival metadata (never hard-delete clinical records) ---
    is_active = models.BooleanField(default=True, db_index=True)
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,  # protect the survivor from accidental deletes
        related_name="merged_children",
    )
    merged_at = models.DateTimeField(null=True, blank=True)

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Manager
    objects: PatientManager = PatientManager()

    class Meta:
        ordering = ["family_name", "given_name", "id"]
        # pragmatic indexes to speed up duplicate checks and lookups
        indexes = [
            models.Index(fields=["family_name", "given_name"]),
            models.Index(fields=["date_of_birth"]),
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["external_id"]),
            models.Index(fields=["family_name", "given_name", "date_of_birth"]),  # common dup key
            models.Index(fields=["merged_into"]),
        ]
        constraints = [
            models.CheckConstraint(
                name="patient_not_merged_into_self",
                check=Q(merged_into__isnull=True) | ~Q(pk=F("merged_into")),
            ),
        ]

    # ---------------- Display & compat helpers ---------------- #

    def __str__(self) -> str:
        dob = self.date_of_birth.isoformat() if self.date_of_birth else "—"
        return f"{self.family_name}, {self.given_name} ({dob})"

    @property
    def full_name(self) -> str:
        return f"{self.given_name} {self.family_name}".strip()

    def get_full_name(self) -> str:
        """Compatibility with templates calling user.get_full_name()."""
        return self.full_name

    
    def save(self, *args, **kwargs):
        """
        Normalize string fields so we never try to save NULL into
        NOT NULL CharFields. This lets the views keep using 'or None'
        without breaking the DB constraints.
        """
        string_fields = [
            "email",
            "phone",
            "sex",
            "address_line",
            "city",
            "region",
            "postal_code",
            "country",
        ]

        for field_name in string_fields:
            # Only touch attributes that actually exist on the model
            if hasattr(self, field_name):
                value = getattr(self, field_name)
                if value is None:
                    setattr(self, field_name, "")

        super().save(*args, **kwargs)

     
    # Back-compat aliases if some code expects first_name/last_name
    @property
    def first_name(self) -> str:
        return self.given_name

    @property
    def last_name(self) -> str:
        return self.family_name

    @property
    def initials(self) -> str:
        g = (self.given_name[:1] if self.given_name else "").upper()
        f = (self.family_name[:1] if self.family_name else "").upper()
        return f"{g}{f}"

    @property
    def age_years(self) -> Optional[int]:
        if not self.date_of_birth:
            return None
        today = date.today()
        years = today.year - self.date_of_birth.year
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            years -= 1
        return max(years, 0)

    @property
    def is_archived(self) -> bool:
        # archived = inactive (typically merged into another)
        return not self.is_active

    # ---------------- Merge helpers ---------------- #

    def mark_merged_into(self, target: "Patient") -> None:
        """
        Archive this patient as merged into 'target' and stamp the time.
        This is a low-level helper; normally call the service function that
        reassigns relations before archiving (see patients.services.merge_into).
        """
        if self.pk == target.pk:
            raise ValueError("Cannot merge a patient into itself.")
        self.is_active = False
        self.merged_into = target
        self.merged_at = timezone.now()
        self.save(update_fields=["is_active", "merged_into", "merged_at"])
