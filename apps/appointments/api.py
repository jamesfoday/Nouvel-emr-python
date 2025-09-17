# apps/appointments/api.py
from typing import Any, Dict, List
from datetime import timedelta

from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.filters import OrderingFilter, SearchFilter

from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes

from apps.rbac.permissions import roles_required
from apps.audit.utils import log_event

from .models import Appointment
from .serializers import (
    AppointmentSerializer,
    AppointmentCreateSerializer,
    AppointmentRescheduleSerializer,
)
from .services import conflicting_appointments
from .schemas import (
    AppointmentConflicts409Serializer,
    CreateAppointmentExample,
    RescheduleAppointmentExample,
)
from .ics import calendar_text_for_appointments


@extend_schema_view(
    list=extend_schema(
        summary="List/search appointments (paginated)",
        description=(
            "Filters: date range (`date_from`, `date_to`), `patient_id`, `clinician_id`, `status`, and `q`."
        ),
        parameters=[
            OpenApiParameter(name="date_from", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="date_to", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="patient_id", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="clinician_id", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="status", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(
                name="q",
                description="Search in reason/location",
                required=False,
                type=OpenApiTypes.STR,
            ),
            OpenApiParameter(name="sort", required=False, type=OpenApiTypes.STR),
            OpenApiParameter(name="limit", required=False, type=OpenApiTypes.INT),
            OpenApiParameter(name="offset", required=False, type=OpenApiTypes.INT),
        ],
    ),
    retrieve=extend_schema(
        summary="Get appointment",
        description="Fetch one appointment by id. Emits `appt.view` audit.",
        responses={200: AppointmentSerializer},
    ),
    create=extend_schema(
        summary="Create appointment (conflict-aware)",
        description="Rejects overlaps for same clinician or patient with **409** and a conflicts list.",
        examples=[CreateAppointmentExample],
        responses={201: AppointmentSerializer, 409: AppointmentConflicts409Serializer},
    ),
)
class AppointmentViewSet(viewsets.ModelViewSet):
    """
    I manage appointments with overlap checks and lifecycle actions.
    """
    schema_tags = ["Appointments"]
    queryset = Appointment.objects.select_related("patient", "clinician").all()
    serializer_class = AppointmentSerializer
    permission_classes = [IsAuthenticated, roles_required("clinician", "staff", "admin")]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["reason", "location"]
    ordering_fields = ["start", "end", "status", "created_at"]
    ordering = ["-start", "id"]

    # ---- list with manual filters ----
    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())

        # manual filters
        df = request.query_params.get("date_from")
        dt = request.query_params.get("date_to")
        pid = request.query_params.get("patient_id")
        cid = request.query_params.get("clinician_id")
        st = request.query_params.get("status")

        if df:
            qs = qs.filter(end__gte=df)
        if dt:
            qs = qs.filter(start__lte=dt)
        if pid:
            qs = qs.filter(patient_id=pid)
        if cid:
            qs = qs.filter(clinician_id=cid)
        if st:
            qs = qs.filter(status=st)

        q = request.query_params.get("q", "").strip()
        if q:
            log_event(request, "appt.search", "Appointment", q)

        page = self.paginate_queryset(qs)
        if page is not None:
            ser = AppointmentSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        return Response(AppointmentSerializer(qs, many=True).data)

    # ---- retrieve ----
    def retrieve(self, request, *args, **kwargs):
        obj = self.get_object()
        log_event(request, "appt.view", "Appointment", obj.id)
        return Response(AppointmentSerializer(obj).data)

    # ---- create with conflict checks ----
    def create(self, request, *args, **kwargs):
        ser = AppointmentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        conflicts = list(
            conflicting_appointments(
                clinician_id=vd["clinician"].id,
                patient_id=vd["patient"].id,
                start=vd["start"],
                end=vd["end"],
            )
        )
        if conflicts:
            return Response(
                {
                    "detail": "Time slot conflicts with existing appointments.",
                    "conflicts": [
                        {
                            "id": c.id,
                            "patient": c.patient_id,
                            "clinician": c.clinician_id,
                            "start": c.start,
                            "end": c.end,
                            "status": c.status,
                        }
                        for c in conflicts[:10]
                    ],
                    "hint": "Pick a free slot or reschedule conflicting entries.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        obj = ser.save()
        log_event(request, "appt.create", "Appointment", obj.id)
        return Response(AppointmentSerializer(obj).data, status=status.HTTP_201_CREATED)

    # ---- reschedule ----
    @extend_schema(
        methods=["POST"],
        summary="Reschedule appointment",
        description="Moves start/end if there’s no conflict; otherwise returns **409** with conflicts list.",
        request=AppointmentRescheduleSerializer,
        examples=[RescheduleAppointmentExample],
        responses={200: AppointmentSerializer, 409: AppointmentConflicts409Serializer},
    )
    @action(detail=True, methods=["post"], url_path="reschedule")
    def reschedule(self, request, pk=None):
        obj = self.get_object()
        ser = AppointmentRescheduleSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        vd = ser.validated_data

        conflicts = list(
            conflicting_appointments(
                clinician_id=obj.clinician_id,
                patient_id=obj.patient_id,
                start=vd["start"],
                end=vd["end"],
                exclude_id=obj.id,
            )
        )
        if conflicts:
            return Response(
                {
                    "detail": "New time conflicts with existing appointments.",
                    "conflicts": [
                        {
                            "id": c.id,
                            "patient": c.patient_id,
                            "clinician": c.clinician_id,
                            "start": c.start,
                            "end": c.end,
                            "status": c.status,
                        }
                        for c in conflicts[:10]
                    ],
                    "hint": "Pick a free slot or adjust the duration.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        obj.start = vd["start"]
        obj.end = vd["end"]
        if vd.get("reason"):
            obj.reason = vd["reason"]
        obj.save(update_fields=["start", "end", "reason", "updated_at"])
        log_event(request, "appt.reschedule", "Appointment", obj.id)
        return Response(AppointmentSerializer(obj).data)

    # ---- cancel ----
    @extend_schema(
        methods=["POST"],
        summary="Cancel appointment",
        description="Sets status to cancelled.",
        responses={200: AppointmentSerializer},
    )
    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        obj = self.get_object()
        obj.status = "cancelled"
        obj.save(update_fields=["status", "updated_at"])
        log_event(request, "appt.cancel", "Appointment", obj.id)
        return Response(AppointmentSerializer(obj).data)

    # ---- single appointment ICS ----
    @extend_schema(
        methods=["GET"],
        summary="Download ICS for this appointment",
        description="I return a .ics file for the appointment (UTC).",
        responses={(200, "text/calendar"): OpenApiTypes.BINARY},  # <-- older Spectacular-friendly
    )
    @action(detail=True, methods=["get"], url_path="ics")
    def ics(self, request, pk=None):
        appt = self.get_object()
        ics_text = calendar_text_for_appointments([appt])
        resp = HttpResponse(ics_text, content_type="text/calendar; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="appointment-{appt.id}.ics"'
        log_event(request, "appt.ics", "Appointment", appt.id)
        return resp

    # ---- clinician feed ICS (date range) ----
    @extend_schema(
        methods=["GET"],
        summary="ICS feed for a clinician (date range)",
        description=(
            "I return a multi-event .ics for a clinician. "
            "Filters: `date_from`, `date_to` (ISO 8601) and optional `status` "
            "(`scheduled`, `confirmed`, `completed`, `cancelled`). "
            "Defaults to the next 7 days if no range given."
        ),
        parameters=[
            OpenApiParameter(name="date_from", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="date_to", required=False, type=OpenApiTypes.DATETIME),
            OpenApiParameter(name="status", required=False, type=OpenApiTypes.STR),
        ],
        responses={(200, "text/calendar"): OpenApiTypes.BINARY},  # <-- tuple form
    )
    @action(detail=False, methods=["get"], url_path=r"clinician/(?P<clinician_id>[^/.]+)/ics")
    def clinician_ics(self, request, clinician_id=None):
        now = timezone.now()
        raw_from = request.query_params.get("date_from")
        raw_to = request.query_params.get("date_to")
        status_filter = request.query_params.get("status")

        df = parse_datetime(raw_from) if raw_from else now
        dt = parse_datetime(raw_to) if raw_to else (now + timedelta(days=7))
        if df and df.tzinfo is None:
            df = timezone.make_aware(df)
        if dt and dt.tzinfo is None:
            dt = timezone.make_aware(dt)

        qs = (
            self.get_queryset()
            .filter(clinician_id=clinician_id, start__lt=dt, end__gt=df)
            .order_by("start")
        )
        if status_filter:
            qs = qs.filter(status=status_filter)

        ics_text = calendar_text_for_appointments(qs)
        resp = HttpResponse(ics_text, content_type="text/calendar; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="clinician-{clinician_id}.ics"'
        log_event(request, "appt.ics_feed", "Appointment", str(clinician_id))
        return resp
