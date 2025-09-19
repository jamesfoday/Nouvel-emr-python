# apps/patients/ui.py
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils.decorators import method_decorator
from django.views import View

from .models import Patient
from apps.appointments.models import Appointment

@method_decorator(login_required, name="dispatch")
class PatientsListView(View):
    template_full = "patients/list.html"
    template_partial = "patients/_table.html"

    def get(self, request):
        q = (request.GET.get("q") or "").strip()
        page_num = request.GET.get("page") or 1

        qs = Patient.objects.all()
        if q:
            qs = qs.filter(
                Q(family_name__istartswith=q)
                | Q(given_name__istartswith=q)
                | Q(email__icontains=q)
                | Q(phone__icontains=q)
                | Q(external_id__icontains=q)
            )

        paginator = Paginator(qs, 25)
        page = paginator.get_page(page_num)

        ctx = {"q": q, "page": page}
        # HTMX requests only need the table fragment
        if request.headers.get("Hx-Request"):
            return render(request, self.template_partial, ctx)
        return render(request, self.template_full, ctx)


@method_decorator(login_required, name="dispatch")
class PatientDetailView(View):
    template_name = "patients/detail.html"

    def get(self, request, pk: int):
        patient = get_object_or_404(Patient, pk=pk)
        appts = (
            Appointment.objects.select_related("clinician")
            .filter(patient=patient)
            .order_by("-start")[:50]
        )
        return render(request, self.template_name, {"patient": patient, "appointments": appts})
