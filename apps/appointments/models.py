# apps/appointments/models.py
from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.utils import timezone


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    # I bind the appointment to a patient and a clinician (user).
    patient = models.ForeignKey(
        "patients.Patient", on_delete=models.CASCADE, related_name="appointments"
    )
    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments"
    )

    # I keep timezone-aware datetimes (Django handles this when USE_TZ=True).
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
        constraints = [
            # I never allow end <= start; this protects data at the DB level.
            models.CheckConstraint(check=Q(end__gt=F("start")), name="appt_end_after_start"),
        ]
        ordering = ["-start", "id"]

    def __str__(self) -> str:
        return f"{self.patient} @ {self.start.isoformat()} → {self.end.isoformat()} ({self.status})"

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def overlaps(self, other_start, other_end) -> bool:
        # I treat intervals as [start, end); end == start is fine (no clash).
        return self.start < other_end and other_start < self.end

    @property
    def duration_minutes(self) -> int:
        # I expose a quick duration helper for serializers/UI.
        delta = self.end - self.start
        return int(delta.total_seconds() // 60)


class Availability(models.Model):
    """
    I capture a clinician’s recurring weekly availability.
    Example: Monday 09:00–17:00 with 30-minute slots.
    """

    # 0=Mon ... 6=Sun (Python’s weekday())
    WEEKDAY_CHOICES = [
        (0, "Mon"),
        (1, "Tue"),
        (2, "Wed"),
        (3, "Thu"),
        (4, "Fri"),
        (5, "Sat"),
        (6, "Sun"),
    ]

    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_windows"
    )
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    # default slot size for suggestions; clients can override per request.
    slot_minutes = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["clinician", "weekday"]),
        ]
        constraints = [
            models.CheckConstraint(check=Q(end_time__gt=F("start_time")), name="avail_end_after_start"),
        ]
        ordering = ["clinician", "weekday", "start_time"]

    def __str__(self) -> str:
        return f"{self.clinician_id}@{self.get_weekday_display()} {self.start_time}-{self.end_time} ({self.slot_minutes}m)"
