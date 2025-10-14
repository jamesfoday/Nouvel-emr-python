from django.conf import settings
from django.db import models
from django.utils import timezone
from apps.patients.models import Patient

class Encounter(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"

    clinician = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="encounters")
    patient   = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="encounters")

    start = models.DateTimeField(default=timezone.now)
    end   = models.DateTimeField(blank=True, null=True)

    reason   = models.CharField(max_length=200, blank=True)
    location = models.CharField(max_length=120, blank=True)
    status   = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start"]
        indexes = [models.Index(fields=["clinician", "start"]), models.Index(fields=["patient", "start"])]

    def __str__(self):
        return f"Encounter #{self.pk} – {self.patient} – {self.start:%Y-%m-%d %H:%M}"

class VitalSign(models.Model):
    encounter = models.OneToOneField(Encounter, on_delete=models.CASCADE, related_name="vitals")
    systolic   = models.PositiveIntegerField(blank=True, null=True)   # mmHg
    diastolic  = models.PositiveIntegerField(blank=True, null=True)   # mmHg
    heart_rate = models.PositiveIntegerField(blank=True, null=True)   # bpm
    resp_rate  = models.PositiveIntegerField(blank=True, null=True)   # breaths/min
    temperature_c = models.DecimalField(max_digits=4, decimal_places=1, blank=True, null=True)
    spo2       = models.PositiveIntegerField(blank=True, null=True)   # %
    weight_kg  = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True)
    height_cm  = models.DecimalField(max_digits=5, decimal_places=1, blank=True, null=True)
    updated_at = models.DateTimeField(auto_now=True)

class ClinicalNote(models.Model):
    class Kind(models.TextChoices):
        SUBJECTIVE = "S", "Subjective"
        OBJECTIVE  = "O", "Objective"
        ASSESSMENT = "A", "Assessment"
        PLAN       = "P", "Plan"
        GENERAL    = "N", "Note"

    encounter = models.ForeignKey(Encounter, on_delete=models.CASCADE, related_name="notes")
    author    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind      = models.CharField(max_length=1, choices=Kind.choices, default=Kind.GENERAL)
    content   = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
