# apps/patients/ui_views.py
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.http import HttpRequest

from .models import Patient


# ---- helpers ---------------------------------------------------------------

def _to_int(value, default: int, *, min_value: int = 1, max_value: int = 100) -> int:
    """Parse int query params safely."""
    try:
        i = int(value)
    except (TypeError, ValueError):
        return default
    if i < min_value:
        return default
    if max_value is not None and i > max_value:
        i = max_value
    return i


# ---- console shell ---------------------------------------------------------

@login_required
def console_home(request: HttpRequest):
    """Top-level console landing (cards/shortcuts)."""
    # Template path matches your tree: templates/console/console.html
    return render(request, "console/console.html")


# ---- patients console ------------------------------------------------------

@login_required
def patients_home(request: HttpRequest):
    """
    Full-page shell for Patients. The table body is loaded via HTMX.
    We render a few recent patients so the page isn’t empty on first load.
    """
    initial = Patient.objects.order_by("-id")[:10]
    return render(request, "patients/console.html", {"initial_patients": initial})


@login_required
def patients_search(request: HttpRequest):
    """
    HTMX endpoint that returns the table partial with search results.
    Supports:
      - q: search term (name/email/phone/external_id)
      - limit, offset: pagination (lightweight)
    """
    q = (request.GET.get("q") or "").strip()
    limit = _to_int(request.GET.get("limit"), default=25, min_value=5, max_value=100)
    offset = _to_int(request.GET.get("offset"), default=0, min_value=0, max_value=10_000)

    qs = Patient.objects.all()

    if q:
        qs = qs.filter(
            Q(family_name__icontains=q)
            | Q(given_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(external_id__icontains=q)
        )

    # Consistent ordering for a directory-style list
    qs = qs.order_by("family_name", "given_name", "id")

    total = qs.count()
    rows = list(qs[offset: offset + limit])

    ctx = {
        "patients": rows,
        "q": q,
        "limit": limit,
        "offset": offset,
        "total": total,
        "next_offset": offset + limit if (offset + limit) < total else None,
        "prev_offset": offset - limit if (offset - limit) >= 0 else None,
    }
    return render(request, "patients/_table.html", ctx)
