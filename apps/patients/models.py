# apps/patients/models.py
from django.db import models
from django.utils import timezone
from django.db.models import Q, F


class Patient(models.Model):
    # --- Core demographics  capture up front for intake & search ---
    given_name = models.CharField(max_length=100)
    family_name = models.CharField(max_length=100)
    date_of_birth = models.DateField(null=True, blank=True)
    sex = models.CharField(max_length=20, blank=True, default="")  #  keeping this free text for now

    # --- Contact identifiers ( normalized at the service layer for now) ---
    phone = models.CharField(max_length=50, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    external_id = models.CharField(max_length=64, blank=True, default="")  # e.g., MRN from another system

    # --- Lightweight address bundle (can normalize later if needed) ---
    address_line = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    region = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="")

    # --- Merge / archival metadata ( never hard-delete clinical records) ---
    is_active = models.BooleanField(default=True, db_index=True)
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,  #  protect the survivor from accidental delete cascades
        related_name="merged_children",
    )
    merged_at = models.DateTimeField(null=True, blank=True)

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # add pragmatic indexes to speed up duplicate checks and lookups.
        indexes = [
            models.Index(fields=["family_name", "given_name"]),
            models.Index(fields=["date_of_birth"]),
            models.Index(fields=["email"]),
            models.Index(fields=["phone"]),
            models.Index(fields=["external_id"]),
            models.Index(fields=["family_name", "given_name", "date_of_birth"]),  # common dup key
            models.Index(fields=["merged_into"])
        ]
        ordering = ["family_name", "given_name", "id"]

        constraints = [
        models.CheckConstraint(
            name="patient_not_merged_into_self",
            check=Q(merged_into__isnull=True) | ~Q(pk=F("merged_into")),
        ),
     ]

    def __str__(self) -> str:
        # prefer a compact card-like label for list screens.
        dob = self.date_of_birth.isoformat() if self.date_of_birth else "—"
        return f"{self.family_name}, {self.given_name} ({dob})"

    @property
    def is_archived(self) -> bool:
        # consider an archived record as inactive (typically merged into another).
        return not self.is_active

    def mark_merged_into(self, target: "Patient") -> None:
        # archive this patient as merged into 'target' and stamp the time.
        self.is_active = False
        self.merged_into = target
        self.merged_at = timezone.now()
        self.save(update_fields=["is_active", "merged_into", "merged_at"])
