from django.db import models
from django.conf import settings

class LabCatalog(models.Model):
    code = models.CharField(max_length=64, unique=True)          # e.g. "CBC"
    name = models.CharField(max_length=255)                       # "CBC with differential"
    loinc_code = models.CharField(max_length=64, blank=True, default="")
    is_panel = models.BooleanField(default=False)
    def __str__(self): return f"{self.code} — {self.name}"

class LabOrder(models.Model):
    patient   = models.ForeignKey("patients.Patient", on_delete=models.PROTECT)
    clinician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    catalog   = models.ForeignKey(LabCatalog, on_delete=models.PROTECT)
    priority  = models.CharField(max_length=16, default="routine")
    reason    = models.CharField(max_length=255, blank=True, default="")
    notes     = models.TextField(blank=True, default="")
    status    = models.CharField(
        max_length=16,
        choices=[("draft","Draft"),("ordered","Ordered"),("collected","Collected"),
                 ("in_progress","In progress"),("completed","Completed"),("cancelled","Cancelled")],
        default="ordered",
        db_index=True,
    )
    ordered_at = models.DateTimeField(auto_now_add=True)

    class Priority(models.TextChoices):
        ROUTINE = "routine", "Routine"
        URGENT  = "urgent",  "Urgent"
        STAT    = "stat",    "STAT"

    priority = models.CharField(
        max_length=16,
        choices=Priority.choices,
        default=Priority.ROUTINE,
    )


    class Status(models.TextChoices):
        ORDERED   = "ordered",   "Ordered"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELED  = "canceled",  "Canceled"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ORDERED,
    )

class Specimen(models.Model):
    order        = models.OneToOneField(LabOrder, on_delete=models.CASCADE, related_name="specimen")
    type         = models.CharField(max_length=64)                # blood/urine
    collected_at = models.DateTimeField(null=True, blank=True)
    identifier   = models.CharField(max_length=64, blank=True, default="")  # barcode

class DiagnosticReport(models.Model):
    class Status(models.TextChoices):
        FINAL     = "final",     "Final"
        PARTIAL   = "partial",   "Partial"
        CORRECTED = "corrected", "Corrected"

    order          = models.ForeignKey("LabOrder", on_delete=models.PROTECT, related_name="reports", null=True, blank=True)
    patient        = models.ForeignKey("patients.Patient", on_delete=models.PROTECT)
    status         = models.CharField(max_length=16, choices=Status.choices, default=Status.FINAL)
    issued_at      = models.DateTimeField(auto_now_add=True)
    performing_lab = models.CharField(max_length=255, blank=True, default="")
    pdf            = models.FileField(upload_to="lab_reports/", blank=True, null=True)

class Observation(models.Model):
    report    = models.ForeignKey(DiagnosticReport, on_delete=models.CASCADE, related_name="observations")
    code      = models.CharField(max_length=64, blank=True, default="")     # LOINC
    name      = models.CharField(max_length=255)                             # “Hemoglobin”
    value_num = models.FloatField(null=True, blank=True)
    value_text= models.CharField(max_length=255, blank=True, default="")
    unit      = models.CharField(max_length=32, blank=True, default="")      # UCUM
    ref_low   = models.FloatField(null=True, blank=True)
    ref_high  = models.FloatField(null=True, blank=True)
    flag      = models.CharField(max_length=16, blank=True, default="")      # H/L/crit
    note      = models.CharField(max_length=255, blank=True, default="")



class ExternalLabResult(models.Model):
    class Status(models.TextChoices):
        SUBMITTED     = "submitted", "Submitted"
        UNDER_REVIEW  = "under_review", "Under review"
        ACCEPTED      = "accepted", "Accepted"
        REJECTED      = "rejected", "Rejected"

    # who the result is about
    patient        = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="external_results",
    )

    # optional: attach to a specific order
    order          = models.ForeignKey(
        "labs.LabOrder",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="external_results",
    )

    # which clinician should receive/review it
    clinician_to   = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="external_results_inbox",
    )

    # patient-entered meta
    title          = models.CharField(max_length=200, blank=True)
    vendor_name    = models.CharField(max_length=200, blank=True, help_text="Lab/facility name")
    performed_at   = models.DateTimeField(null=True, blank=True)
    file           = models.FileField(upload_to="external_results/%Y/%m/%d/")
    notes          = models.TextField(blank=True)

    # lifecycle
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED)
    created_at     = models.DateTimeField(auto_now_add=True)
    updated_at     = models.DateTimeField(auto_now=True)
    reviewed_at    = models.DateTimeField(null=True, blank=True)
    reviewer       = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="external_results_reviewed",
    )

    # patient-side soft delete (clinician inbox still keeps it)
    is_deleted_by_patient = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        base = self.title or (self.order and self.order.catalog.name) or "External result"
        return f"{base} — {self.patient}"


      