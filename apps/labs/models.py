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

class Specimen(models.Model):
    order        = models.OneToOneField(LabOrder, on_delete=models.CASCADE, related_name="specimen")
    type         = models.CharField(max_length=64)                # blood/urine
    collected_at = models.DateTimeField(null=True, blank=True)
    identifier   = models.CharField(max_length=64, blank=True, default="")  # barcode

class DiagnosticReport(models.Model):
    order          = models.ForeignKey(LabOrder, on_delete=models.PROTECT, related_name="reports", null=True, blank=True)
    patient        = models.ForeignKey("patients.Patient", on_delete=models.PROTECT)
    status         = models.CharField(max_length=16, default="final")       # final/partial/corrected
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
