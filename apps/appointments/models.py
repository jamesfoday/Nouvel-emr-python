from django.conf import settings
from django.db import models
from django.utils import timezone

class Appointment(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    #  bind the appointment to a patient and a clinician (user).
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="appointments"
    )
    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments"
    )

    # keep timezone-aware datetimes (Django does the right thing when USE_TZ=True).
    start = models.DateTimeField()
    end = models.DateTimeField()

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    reason = models.CharField(max_length=255, blank=True, default="")
    location = models.CharField(max_length=255, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["start"]),
            models.Index(fields=["end"]),
            models.Index(fields=["status"]),
            models.Index(fields=["clinician", "start"]),
            models.Index(fields=["patient", "start"]),
        ]
        ordering = ["-start", "id"]

    def __str__(self) -> str:
        return f"{self.patient} @ {self.start.isoformat()} → {self.end.isoformat()} ({self.status})"

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def overlaps(self, other_start, other_end) -> bool:
        #  consider intervals [start, end); end==start is OK (no overlap).
        return self.start < other_end and other_start < self.end
