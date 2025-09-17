# apps/patients/schemas.py
# centralize Swagger/OpenAPI examples & inline serializers here
# so /api/docs shows prefilled requests and typed responses.

# apps/patients/schemas.py
from drf_spectacular.utils import OpenApiExample, inline_serializer
from rest_framework import serializers

# ---- shared fields for duplicate candidate ----
_DUP_FIELDS = {
    "id": serializers.IntegerField(),
    "given_name": serializers.CharField(),
    "family_name": serializers.CharField(),
    "date_of_birth": serializers.DateField(allow_null=True),
    "email": serializers.EmailField(allow_blank=True, required=False),
    "phone": serializers.CharField(allow_blank=True, required=False),
    "score": serializers.IntegerField(),
}

# single candidate shape
DuplicateCandidate = inline_serializer(
    name="PatientDuplicateCandidate",
    fields=_DUP_FIELDS,
)

# list of candidates (IMPORTANT: many=True is set here, not at use-site)
DuplicateCandidates = inline_serializer(
    name="PatientDuplicateCandidates",
    fields=_DUP_FIELDS,
    many=True,
)

# 409 response for create-with-duplicates
Create409Response = inline_serializer(
    name="PatientCreateConflict409",
    fields={
        "detail": serializers.CharField(),
        # embed a list of duplicate candidates directly
        "duplicates": inline_serializer(
            name="PatientDuplicateCandidatesFor409",
            fields=_DUP_FIELDS,
            many=True,
        ),
        "hint": serializers.CharField(),
    },
)

# merge proposal shapes
MergeConflict = inline_serializer(
    name="PatientMergeConflict",
    fields={
        "field": serializers.CharField(),
        "primary": serializers.CharField(allow_blank=True, required=False, allow_null=True),
        "other": serializers.CharField(allow_blank=True, required=False, allow_null=True),
    },
)

MergeProposalResponse = inline_serializer(
    name="PatientMergeProposalResponse",
    fields={
        "primary_id": serializers.IntegerField(),
        "other_id": serializers.IntegerField(),
        "proposed": inline_serializer(
            name="PatientMergeProposedFields",
            fields={
                "given_name": serializers.CharField(allow_blank=True, required=False),
                "family_name": serializers.CharField(allow_blank=True, required=False),
                "date_of_birth": serializers.DateField(allow_null=True, required=False),
                "sex": serializers.CharField(allow_blank=True, required=False),
                "phone": serializers.CharField(allow_blank=True, required=False),
                "email": serializers.EmailField(allow_blank=True, required=False),
                "external_id": serializers.CharField(allow_blank=True, required=False),
                "address_line": serializers.CharField(allow_blank=True, required=False),
                "city": serializers.CharField(allow_blank=True, required=False),
                "region": serializers.CharField(allow_blank=True, required=False),
                "postal_code": serializers.CharField(allow_blank=True, required=False),
                "country": serializers.CharField(allow_blank=True, required=False),
            },
        ),
        "conflicts": inline_serializer(
            name="PatientMergeConflicts",
            fields={
                "field": serializers.CharField(),
                "primary": serializers.CharField(allow_blank=True, required=False, allow_null=True),
                "other": serializers.CharField(allow_blank=True, required=False, allow_null=True),
            },
            many=True,
        ),
        "note": serializers.CharField(),
    },
)

# ---- request body examples (prefilled) ----

CreatePatientExample = OpenApiExample(
    "New patient",
    value={
        "given_name": "Jane",
        "family_name": "Doe",
        "date_of_birth": "1990-04-12",
        "sex": "female",
        "phone": "+33 6 12 34 56 78",
        "email": "jane@example.com",
        "external_id": "MRN-001",
        "address_line": "10 Rue de Rivoli",
        "city": "Paris",
        "region": "Île-de-France",
        "postal_code": "75001",
        "country": "FR",
    },
    description="Minimal realistic payload for intake.",
)

CreatePatientConfirmExample = OpenApiExample(
    "Confirm create (bypass duplicate warning)",
    value={
        "given_name": "Jane",
        "family_name": "Doe",
        "date_of_birth": "1990-04-12",
        "email": "jane@example.com",
        "confirm_create": True
    },
    description="Send this after reviewing duplicates to proceed anyway.",
)

CheckDuplicatesExample = OpenApiExample(
    "Duplicate check request",
    value={
        "given_name": "Jane",
        "family_name": "Doe",
        "date_of_birth": "1990-04-12",
        "email": "jane@example.com",
        "phone": "+33 6 12 34 56 78"
    },
)

MergeProposalExample = OpenApiExample(
    "Merge preview request",
    value={"other_id": 42},
    description="Provide the other patient ID to compare with the current (primary) record.",
)
