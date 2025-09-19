# apps/appointments/ui.py
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.utils.decorators import method_decorator
from django.views import View

from .models import Appointment

@method_decorator(login_required, name="dispatch")
class AppointmentsListView(View):
    template_full = "appointments/list.html"
    template_partial = "appointments/_table.html"

    def get(self, request):
        q = (request.GET.get("q") or "").strip()
        page_num = request.GET.get("page") or 1
        df_raw = request.GET.get("date_from")
        dt_raw = request.GET.get("date_to")
        status = request.GET.get("status")

        qs = Appointment.objects.select_related("patient", "clinician").all()

        if q:
            qs = qs.filter(Q(reason__icontains=q) | Q(location__icontains=q)
                           | Q(patient__family_name__icontains=q)
                           | Q(patient__given_name__icontains=q))

        if df_raw:
            df = parse_datetime(df_raw)
            if df:
                qs = qs.filter(end__gte=df)
        if dt_raw:
            dt = parse_datetime(dt_raw)
            if dt:
                qs = qs.filter(start__lte=dt)
        if status:
            qs = qs.filter(status=status)

        qs = qs.order_by("-start", "id")
        paginator = Paginator(qs, 25)
        page = paginator.get_page(page_num)

        ctx = {"q": q, "page": page, "date_from": df_raw or "", "date_to": dt_raw or "", "status": status or ""}
        if request.headers.get("Hx-Request"):
            return render(request, self.template_partial, ctx)
        return render(request, self.template_full, ctx)
