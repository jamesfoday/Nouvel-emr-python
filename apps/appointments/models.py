# apps/appointments/models.py
from django.conf import settings
from django.db import models
from django.db.models import Q, F


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("confirmed", "Confirmed"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    # Links
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="appointments",
    )
    clinician = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="appointments",
    )

    # Time window (timezone-aware; Django handles this when USE_TZ=True)
    start = models.DateTimeField()
    end = models.DateTimeField()

    # Details
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    reason = models.CharField(max_length=255, blank=True, default="")
    location = models.CharField(max_length=255, blank=True, default="")

    # Email reminder bookkeeping (optional)
    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_2h_sent_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
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
            # Never allow end <= start (DB-level guard) — use condition= (Django 6+ safe)
            models.CheckConstraint(
                name="appt_end_after_start",
                condition=Q(end__gt=F("start")),
            ),
        ]
        ordering = ["-start", "id"]

    def __str__(self) -> str:
        return f"{self.patient} @ {self.start.isoformat()} → {self.end.isoformat()} ({self.status})"

    def is_cancelled(self) -> bool:
        return self.status == "cancelled"

    def overlaps(self, other_start, other_end) -> bool:
        # Intervals are [start, end); end == start = no overlap
        return self.start < other_end and other_start < self.end

    @property
    def duration_minutes(self) -> int:
        delta = self.end - self.start
        return int(delta.total_seconds() // 60)


class Availability(models.Model):
    """
    Recurring weekly availability for a clinician.
    Example: Monday 09:00–17:00 with 30-minute slots.
    """

    # 0=Mon ... 6=Sun (matches Python’s weekday())
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
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="availability_windows",
    )
    weekday = models.IntegerField(choices=WEEKDAY_CHOICES)
    start_time = models.TimeField()
    end_time = models.TimeField()

    # Default slot size for suggestions; UI can override
    slot_minutes = models.PositiveIntegerField(default=30)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["clinician", "weekday"]),
        ]
        constraints = [
            # End must be after start (DB-level guard) — use condition=
            models.CheckConstraint(
                name="avail_end_after_start",
                condition=Q(end_time__gt=F("start_time")),
            ),
            # Avoid exact duplicate windows for the same clinician/day
            models.UniqueConstraint(
                name="uniq_availability_window",
                fields=["clinician", "weekday", "start_time", "end_time"],
            ),
        ]
        ordering = ["clinician", "weekday", "start_time"]

    def __str__(self) -> str:
        return f"{self.clinician_id}@{self.get_weekday_display()} {self.start_time}-{self.end_time} ({self.slot_minutes}m)"
