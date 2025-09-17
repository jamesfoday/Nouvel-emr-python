# apps/patients/serializers.py
from rest_framework import serializers
from .models import Patient

class PatientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Patient
        fields = [
            "id", "given_name", "family_name", "date_of_birth", "sex",
            "phone", "email", "external_id",
            "address_line", "city", "region", "postal_code", "country",
            # read-only merge metadata
            "is_active", "merged_into", "merged_at",
            "created_at", "updated_at",  
        ]
        read_only_fields = ["is_active", "merged_into", "merged_at", "id"]
