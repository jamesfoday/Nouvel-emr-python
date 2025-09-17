from typing import Any, Dict, List

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from apps.rbac.permissions import roles_required
from apps.audit.utils import log_event
from .models import Patient
from .serializers import PatientSerializer
from .services import find_possible_duplicates, score_duplicate


class PatientViewSet(viewsets.ModelViewSet):
    """
    Requires one of: admin, clinician, staff (or superuser).
    """
    queryset = Patient.objects.all()
    serializer_class = PatientSerializer
    permission_classes = [IsAuthenticated, roles_required("clinician", "staff", "admin")]

    # ---- Helpers ----

    def _is_confirmed(self, request) -> bool:
        # I accept either a boolean field or a header; clients can choose.
        body_flag = request.data.get("confirm_create")
        hdr_flag = request.headers.get("X-Confirm-Create", "")
        truthy = {"true", "1", "yes", "y", True}
        return (body_flag in truthy) or (str(body_flag).lower() in truthy) or (hdr_flag.lower() in truthy)

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
                        email=payload.get("email", ""),
                        phone=payload.get("phone", ""),
                        given_name=payload.get("given_name", ""),
                        family_name=payload.get("family_name", ""),
                        dob=payload.get("date_of_birth"),
                    ),
                }
            )
        results.sort(key=lambda r: r["score"], reverse=True)
        return results

    # ---- List/Search ----

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

    # ---- Retrieve ----

    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        log_event(request, "patient.view", "Patient", obj.id)
        return Response(PatientSerializer(obj).data)

    # ---- Create with inline duplicate warning ----

    def create(self, request, *args, **kwargs):
        # validate first so types/format are correct before duplicate logic.
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        # run a duplicate preflight unless the client explicitly confirms creation.
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

    # ---- Update (audit) ----

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

    # ---- Merge proposal (preview) ----

    @action(detail=True, methods=["post"], url_path="merge-proposal")
    def merge_proposal(self, request, pk=None):
        """
        I return a proposed merged record and list any conflicting fields.
        This does NOT write to the DB. Client can review before building a real merge flow.
        """
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
            # prefer primary's non-empty value; otherwise take other's.
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
