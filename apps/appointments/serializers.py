from rest_framework import serializers
from .models import Appointment

class AppointmentSerializer(serializers.ModelSerializer):
    # I accept IDs for patient/clinician; DRF will map them to FKs.
    class Meta:
        model = Appointment
        fields = [
            "id", "patient", "clinician",
            "start", "end",
            "status", "reason", "location",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "status"]

class AppointmentCreateSerializer(serializers.ModelSerializer):
    # I let clients set status optionally; default is scheduled.
    status = serializers.ChoiceField(choices=[c[0] for c in Appointment.STATUS_CHOICES], required=False)

    class Meta:
        model = Appointment
        fields = ["patient", "clinician", "start", "end", "status", "reason", "location"]

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "End must be after start."})
        return attrs

class AppointmentRescheduleSerializer(serializers.Serializer):
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["end"] <= attrs["start"]:
            raise serializers.ValidationError({"end": "End must be after start."})
        return attrs
