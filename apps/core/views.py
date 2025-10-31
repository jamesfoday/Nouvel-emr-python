# apps/core/views.py
from django.conf import settings
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages
from django.urls import reverse
from django.db.models import Prefetch

# Services
from apps.services.models import Service

# Try to import ServiceSection for ordered prefetch (safe fallback if not found)
try:
    from apps.services.models import ServiceSection  # expected section model
except Exception:
    ServiceSection = None

# Try to import your existing InquiryForm (adjust if your app path differs)
try:
    from apps.inquiry.forms import InquiryForm  # common path
except Exception:
    try:
        from apps.inquiry import InquiryForm
    except Exception:
        InquiryForm = None


def _service_image_url(s):
    """
    Pick the first available image-ish field; fall back to a static placeholder.
    Works with FileSystemStorage or Cloudinary.
    """
    for attr in ("hero_image", "cover", "image", "photo", "thumbnail", "icon"):
        f = getattr(s, attr, None)
        try:
            if f and getattr(f, "url", None):
                return f.url
        except Exception:
            # Storage backends can raise if file missing; ignore and continue
            pass
    return "/static/img/placeholders/service-card.png"


def _service_snippet(s):
    """
    Choose a short description for the grid:
      1) s.summary (if exists and non-empty)
      2) first section's description (ordered), if available
      3) s.description (if exists)
      4) None -> template will show 'Details coming soon.'
    """
    # 1) Explicit summary on Service
    summary = getattr(s, "summary", None)
    if summary:
        return summary

    # 2) First section's description
    try:
        # If we prefetched with ordering, .all() is already sorted
        first_sec = next(iter(s.sections.all()), None)
        if first_sec:
            desc = getattr(first_sec, "description", None)
            if desc:
                return desc
    except Exception:
        pass

    # 3) Fallback to a description field on Service if present
    desc = getattr(s, "description", None)
    if desc:
        return desc

    # 4) Nothing — template will fall back to 'Details coming soon.'
    return None


def home(request):
    # ---------- Static chips/cards used by the homepage sections ----------
    diag_tests = ["EKG", "Strep", "Ultrasound", "Spirometry", "Pregnancy Test"]
    hemat_params = ["WBC DIFF", "H. Pylori", "CBC"]
    feature_cards = [
        {"icon": "🌿", "title": "Book in minutes", "desc": "A modern, smooth flow from start to finish."},
        {"icon": "🔒", "title": "Chat securely", "desc": "Encrypted messaging with your care team."},
        {"icon": "⚡", "title": "View results fast", "desc": "Same-day lab results for many tests."},
    ]

    # ---------- Services grid (latest 6) ----------
    # Order newest first and prefetch sections in a deterministic order
    if ServiceSection:
        sections_prefetch = Prefetch(
            "sections",
            queryset=ServiceSection.objects.order_by("order", "id"),
        )
        services_qs = Service.objects.all().order_by("-created_at").prefetch_related(sections_prefetch)
    else:
        services_qs = Service.objects.all().order_by("-created_at").prefetch_related("sections")

    services_total = services_qs.count()

    # Build a lightweight list for the template
    services_grid = []
    for s in services_qs[:6]:
        services_grid.append(
            {
                "title": getattr(s, "title", "Untitled service"),
                "slug": getattr(s, "slug", None),
                "image_url": _service_image_url(s),
                # Precompute snippet so the template can just render it
                "snippet": _service_snippet(s),
                # Keep raw fields in case you also want to use them in templates
                "summary": getattr(s, "summary", None),
                "description": getattr(s, "description", None),
            }
        )

    # ---------- Inquiry form (reuse your existing Inquiry stack) ----------
    form = None
    if request.method == "POST" and InquiryForm is not None:
        form = InquiryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Thanks! Your inquiry has been sent.")
            return redirect(request.path)
    else:
        form = InquiryForm() if InquiryForm is not None else None

    ctx = {
        "diag_tests": diag_tests,
        "hemat_params": hemat_params,
        "feature_cards": feature_cards,
        "services_grid": services_grid,     # list of up to 6 services for the homepage card UI
        "services_total": services_total,   # use in template to conditionally show “See all”
        "services_catalog_url": reverse("services:catalog"),  # public browse view
        "year": timezone.now().year,
        "form": form,  # None if InquiryForm couldn't be imported; template can handle gracefully
    }
    return render(request, "home.html", ctx)
