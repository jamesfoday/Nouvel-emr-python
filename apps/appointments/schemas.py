# apps/appointments/schemas.py
from rest_framework import serializers
from drf_spectacular.utils import OpenApiExample


# I describe a single conflicting appointment in 409 responses.
class AppointmentConflictItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    patient = serializers.IntegerField()
    clinician = serializers.IntegerField()
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    status = serializers.CharField()


# I describe the whole 409 payload (detail + list of conflicts + hint).
class AppointmentConflicts409Serializer(serializers.Serializer):
    detail = serializers.CharField()
    conflicts = AppointmentConflictItemSerializer(many=True)
    hint = serializers.CharField()


# ---- Swagger example payloads ----

CreateAppointmentExample = OpenApiExample(
    "Create appointment",
    value={
        "patient": 1,
        "clinician": 2,
        "start": "2025-09-20T09:00:00Z",
        "end": "2025-09-20T09:30:00Z",
        "reason": "Initial consultation",
        "location": "Room 3",
    },
)

RescheduleAppointmentExample = OpenApiExample(
    "Reschedule",
    value={
        "start": "2025-09-21T10:00:00Z",
        "end": "2025-09-21T10:30:00Z",
        "reason": "Patient requested later time",
    },
)
