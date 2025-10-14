# apps/patients/views.py
from django.shortcuts import render
from django.db.models import Q
from .models import Patient


def _int_param(value, default=10, minimum=1, maximum=50):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(n, maximum))


def search(request):
    """
    HTMX search endpoint for selecting a patient.
    - Matches across given/family name, phone, email, external_id.
    - Excludes merged/inactive patients.
    - Respects ?limit= (default 10, max 50).
    """
    q = (request.GET.get("q") or "").strip()
    limit = _int_param(request.GET.get("limit"), default=10, maximum=50)

    queryset = Patient.objects.filter(is_active=True, merged_into__isnull=True)

    if q:
        terms = q.split()
        cond = Q()
        for t in terms:
            cond &= (
                Q(given_name__icontains=t)
                | Q(family_name__icontains=t)
                | Q(phone__icontains=t)
                | Q(email__icontains=t)
                | Q(external_id__icontains=t)
            )
        queryset = queryset.filter(cond)

    patients = queryset.order_by("family_name", "given_name", "id")[:limit]

    return render(request, "patients/_search_results.html", {
        "patients": patients,
        "q": q,
    })
