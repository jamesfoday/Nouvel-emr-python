# apps/appointments/serializers.py
from __future__ import annotations

from rest_framework import serializers
from .models import Appointment, Availability


class AppointmentSerializer(serializers.ModelSerializer):
    # I expose a computed duration so UIs don’t have to do date math.
    duration_minutes = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "patient",
            "clinician",
            "start",
            "end",
            "status",
            "reason",
            "location",
            "created_at",
            "updated_at",
            "duration_minutes",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "duration_minutes"]

    def get_duration_minutes(self, obj: Appointment) -> int:
        delta = obj.end - obj.start
        return int(delta.total_seconds() // 60)


class AppointmentCreateSerializer(serializers.ModelSerializer):
    # I let clients set status optionally; default is "scheduled".
    status = serializers.ChoiceField(
        choices=[c[0] for c in Appointment.STATUS_CHOICES],
        required=False,
    )

    class Meta:
        model = Appointment
        fields = ["patient", "clinician", "start", "end", "status", "reason", "location"]

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "End must be after start."})
        return attrs

    def create(self, validated_data):
        # Default status if omitted.
        validated_data.setdefault("status", "scheduled")
        return super().create(validated_data)


class AppointmentRescheduleSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "End must be after start."})
        return attrs


class AvailabilitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Availability
        fields = [
            "id",
            "clinician",
            "weekday",
            "start_time",
            "end_time",
            "slot_minutes",
            "is_active",
        ]


class FreeSlotSerializer(serializers.Serializer):
    # I match the dicts produced by services.get_free_slots
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField()
    clinician = serializers.IntegerField()
