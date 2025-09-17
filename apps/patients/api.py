# apps/patients/api.py
from typing import Any, Dict, List

from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiExample,
)
from drf_spectacular.types import OpenApiTypes

from apps.rbac.permissions import roles_required
from apps.audit.utils import log_event
from .models import Patient
from .serializers import PatientSerializer
from .services import find_possible_duplicates, score_duplicate
from .schemas import (
    CreatePatientExample,
    CreatePatientConfirmExample,
    CheckDuplicatesExample,
    MergeProposalExample,
    Create409Response,
    DuplicateCandidates,
    MergeProposalResponse,
)


@extend_schema_view(
    list=extend_schema(
        summary="Search patients",
        description="Quick search across family/given name, email, phone, external_id.",
        parameters=[
            OpenApiParameter(
                name="q",
                description="Search term (e.g., name/email/phone).",
                required=False,
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
            )
        ],
        responses={200: PatientSerializer(many=True)},
    ),
    retrieve=extend_schema(
        summary="Get patient",
        description="Fetch a patient by id. Emits `patient.view` audit.",
        responses={200: PatientSerializer},
    ),
    create=extend_schema(
        summary="Create patient (with inline duplicate warning)",
        description=(
            "Create patient. If likely duplicates are found, returns **409** with a candidates list. "
            "To proceed anyway, pass `confirm_create=true` (or header `X-Confirm-Create: true`)."
        ),
        examples=[CreatePatientExample, CreatePatientConfirmExample],
        responses={201: PatientSerializer, 409: Create409Response},
    ),
    partial_update=extend_schema(
        summary="Update patient (partial)",
        description="Patch patient. Emits `patient.update` audit.",
        responses={200: PatientSerializer},
    ),
    update=extend_schema(
        summary="Update patient",
        description="Replace patient. Emits `patient.update` audit.",
        responses={200: PatientSerializer},
    ),
)
class PatientViewSet(viewsets.ModelViewSet):
    """
    Requires one of: admin, clinician, staff (or superuser).
    """
    schema_tags = ["Patients"]
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated, roles_required("clinician", "staff", "admin")]

    # ---- Helpers -------------------------------------------------------------

    def _is_confirmed(self, request) -> bool:
        # I accept confirmation via body or header; clients can choose.
        body_flag = (request.data or {}).get("confirm_create")
        hdr_flag = (request.headers.get("X-Confirm-Create", "") or "").lower()
        truthy = {"true", "1", "yes", "y"}
        return (str(body_flag).lower() in truthy) or (hdr_flag in truthy)

    def _is_merge_confirmed(self, request) -> bool:
        body_flag = (request.data or {}).get("confirm_merge")
        hdr_flag = (request.headers.get("X-Confirm-Merge", "") or "").lower()
        truthy = {"true", "1", "yes", "y"}
        return (str(body_flag).lower() in truthy) or (hdr_flag in truthy)

    def _dup_payload(self, candidates, payload) -> List[Dict[str, Any]]:
        # I return the top 20 candidates with a simple score for the UI to display.
        results = []
        for c in candidates[:20]:
            results.append(
                {
                    "id": c.id,
                    "given_name": c.given_name,
                    "family_name": c.family_name,
                    "date_of_birth": c.date_of_birth,
                    "email": c.email,
                    "phone": c.phone,
                    "score": score_duplicate(
                        c,
                        email=(payload or {}).get("email", ""),
                        phone=(payload or {}).get("phone", ""),
                        given_name=(payload or {}).get("given_name", ""),
                        family_name=(payload or {}).get("family_name", ""),
                        dob=(payload or {}).get("date_of_birth"),
                    ),
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    # ---- List/Search ---------------------------------------------------------

    def list(self, request, *args, **kwargs):
        q = request.query_params.get("q", "").strip()
        qs = self.get_queryset()
        if q:
            from django.db.models import Q
            qs = qs.filter(
                Q(family_name__icontains=q)
                | Q(given_name__icontains=q)
                | Q(email__icontains=q)
                | Q(phone__icontains=q)
                | Q(external_id__icontains=q)
            )
            log_event(request, "patient.search", "Patient", q)
        return Response(PatientSerializer(qs[:100], many=True).data)

    # ---- Retrieve ------------------------------------------------------------

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        log_event(request, "patient.view", "Patient", obj.id)
        return Response(PatientSerializer(obj).data)

    # ---- Create with inline duplicate warning -------------------------------

    def create(self, request, *args, **kwargs):
        # I validate first so types/format are correct before duplicate logic.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        # I run a duplicate preflight unless the client explicitly confirms creation.
        candidates = find_possible_duplicates(
            given_name=vd.get("given_name", ""),
            family_name=vd.get("family_name", ""),
            date_of_birth=vd.get("date_of_birth"),
            email=vd.get("email", ""),
            phone=vd.get("phone", ""),
        )

        if candidates and not self._is_confirmed(request):
            payload = request.data if isinstance(request.data, dict) else {}
            dup_list = self._dup_payload(candidates, payload)
            log_event(request, "patient.duplicate_check", "Patient", "")
            return Response(
                {
                    "detail": "Possible duplicates found. Review before creating.",
                    "duplicates": dup_list,
                    "hint": "Resend with confirm_create=true (or header X-Confirm-Create: true) to proceed.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        # Proceed to create when confirmed or no candidates.
        obj = serializer.save()
        log_event(request, "patient.create", "Patient", obj.id)
        return Response(PatientSerializer(obj).data, status=status.HTTP_201_CREATED)

    # ---- Update (audit) ------------------------------------------------------

    def update(self, request, *args, **kwargs):
        resp = super().update(request, *args, **kwargs)
        try:
            obj = self.get_object()
            log_event(request, "patient.update", "Patient", obj.id)
        except Exception:
            pass
        return resp

    def partial_update(self, request, *args, **kwargs):
        resp = super().partial_update(request, *args, **kwargs)
        try:
            obj = self.get_object()
            log_event(request, "patient.update", "Patient", obj.id)
        except Exception:
            pass
        return resp

    # ---- Duplicate check (pre-create) ---------------------------------------

    @extend_schema(
        methods=["POST"],
        summary="Check duplicates",
        description="Pre-create duplicate check. Returns a ranked list of possible matches.",
        examples=[CheckDuplicatesExample],
        responses={200: DuplicateCandidates},
    )
    @action(detail=False, methods=["post"], url_path="check-duplicates")
    def check_duplicates(self, request):
        data = request.data or {}
        candidates = find_possible_duplicates(
            given_name=data.get("given_name", ""),
            family_name=data.get("family_name", ""),
            date_of_birth=data.get("date_of_birth"),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
        )
        results = []
        for c in candidates[:20]:
            results.append(
                {
                    "id": c.id,
                    "given_name": c.given_name,
                    "family_name": c.family_name,
                    "date_of_birth": c.date_of_birth,
                    "email": c.email,
                    "phone": c.phone,
                    "score": score_duplicate(
                        c,
                        email=data.get("email", ""),
                        phone=data.get("phone", ""),
                        given_name=data.get("given_name", ""),
                        family_name=data.get("family_name", ""),
                        dob=data.get("date_of_birth"),
                    ),
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        log_event(request, "patient.duplicate_check", "Patient", "")
        return Response(results)

    # ---- Merge proposal (preview) -------------------------------------------

    @extend_schema(
        methods=["POST"],
        summary="Merge proposal (preview only)",
        description=(
            "Preview a merge between the current (primary) patient and `other_id`. "
            "Responds with a proposed field set and a list of conflicting fields. **No writes.**"
        ),
        examples=[MergeProposalExample],
        responses={200: MergeProposalResponse},
    )
    @action(detail=True, methods=["post"], url_path="merge-proposal")
    def merge_proposal(self, request, pk=None):
        from django.shortcuts import get_object_or_404

        primary = self.get_object()
        other_id = request.data.get("other_id")
        other = get_object_or_404(Patient, pk=other_id)

        fields = [
            "given_name", "family_name", "date_of_birth", "sex",
            "phone", "email", "external_id",
            "address_line", "city", "region", "postal_code", "country",
        ]

        proposed = {}
        conflicts = []
        for f in fields:
            a = getattr(primary, f)
            b = getattr(other, f)
            # I prefer primary's non-empty value; otherwise take other's.
            chosen = a if (a not in (None, "",)) else b
            proposed[f] = chosen
            # If both non-empty and different, I flag a conflict.
            if a not in (None, "",) and b not in (None, "",) and a != b:
                conflicts.append({"field": f, "primary": a, "other": b})

        payload = {
            "primary_id": primary.id,
            "other_id": other.id,
            "proposed": proposed,
            "conflicts": conflicts,
            "note": "Preview only — no data was saved.",
        }
        return Response(payload, status=200)

    # ---- Merge (writes) ------------------------------------------------------

    @extend_schema(
        methods=["POST"],
        summary="Merge patient (writes)",
        description=(
            "Merge another patient into this one (primary). Archives the other record.\n"
            "Requires `confirm_merge=true` (or header `X-Confirm-Merge: true`).\n\n"
            "**Note:** Related objects are not reassigned in this version."
        ),
        examples=[
            OpenApiExample(
                "Merge request",
                value={"other_id": 42, "confirm_merge": True, "override": {"email": "final@example.com"}},
            )
        ],
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT, 409: OpenApiTypes.OBJECT},
    )
    @action(detail=True, methods=["post"], url_path="merge")
    def merge(self, request, pk=None):
        from django.shortcuts import get_object_or_404

        if not self._is_merge_confirmed(request):
            return Response(
                {
                    "detail": "Merge requires explicit confirmation.",
                    "hint": "Send confirm_merge=true or header X-Confirm-Merge: true.",
                },
                status=409,
            )

        primary = self.get_object()
        other_id = (request.data or {}).get("other_id")
        if not other_id:
            return Response({"detail": "other_id is required."}, status=400)
        if str(primary.id) == str(other_id):
            return Response({"detail": "Cannot merge a patient into itself."}, status=400)

        other = get_object_or_404(Patient, pk=other_id)

        # basic invariants
        if not primary.is_active:
            return Response({"detail": "Primary is not active; cannot receive merge."}, status=400)
        if not other.is_active:
            return Response({"detail": "Other is already archived/merged."}, status=400)
        if other.merged_into_id:
            return Response({"detail": "Other has been merged previously."}, status=400)

        merge_fields = [
            "given_name", "family_name", "date_of_birth", "sex",
            "phone", "email", "external_id",
            "address_line", "city", "region", "postal_code", "country",
        ]
        override = (request.data or {}).get("override", {}) or {}

        with transaction.atomic():
            # choose final values (prefer primary, then other; apply overrides last)
            for f in merge_fields:
                val = getattr(primary, f)
                if (val is None or val == ""):
                    alt = getattr(other, f)
                    if alt not in (None, ""):
                        setattr(primary, f, alt)

            for f, v in override.items():
                if f in merge_fields:
                    setattr(primary, f, v)

            primary.save(update_fields=merge_fields)

            # archive the other
            other.is_active = False
            other.merged_into = primary
            other.merged_at = timezone.now()
            other.save(update_fields=["is_active", "merged_into", "merged_at"])

        log_event(request, "patient.merge", "Patient", primary.id)

        return Response(
            {
                "detail": "Merged successfully.",
                "primary_id": primary.id,
                "archived_id": other.id,
                "note": "Related objects are not reassigned in this version.",
            },
            status=200,
        )
