

from django.conf import settings
from apps.services.models import Service
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib import messages

# Try to import your existing InquiryForm (adjust if your app path differs)
try:
    from apps.inquiry.forms import InquiryForm  # common path
except Exception:
    try:
        from apps.inquiry import InquiryForm  
    except Exception:
        InquiryForm = None  

def _service_image_url(s):
    # prioritize the actual field used in your templates
    for attr in ("hero_image", "cover", "image", "photo", "thumbnail", "icon"):
        f = getattr(s, attr, None)
        try:
            if f and getattr(f, "url", None):
                return f.url
        except Exception:
            pass
    return "/static/img/placeholders/service-card.png"  # make sure this exists


def home(request):
    # --- Static chips/cards used by the homepage sections --------------------
    diag_tests = ["EKG", "Strep", "Ultrasound", "Spirometry", "Pregnancy Test"]
    hemat_params = ["WBC DIFF", "H. Pylori", "CBC"]
    feature_cards = [
        {"icon": "🌿", "title": "Book in minutes", "desc": "A modern, smooth flow from start to finish."},
        {"icon": "🔒", "title": "Chat securely", "desc": "Encrypted messaging with your care team."},
        {"icon": "⚡", "title": "View results fast", "desc": "Same-day lab results for many tests."},
    ]

    # --- Services grid (latest/published) -----------------------------------
    services_grid = []
    try:
        from apps.services.models import Service
        qs = Service.objects.all()
        qs = qs.order_by("-created_at") if hasattr(Service, "created_at") else qs.order_by("title")
        items = []
        for s in qs[:8]:
            items.append({
                "title": getattr(s, "title", "Untitled service"),
                "slug": getattr(s, "slug", None),
                "summary": getattr(s, "summary", None),
                "description": getattr(s, "description", None),
                "image_url": _service_image_url(s),
            })
        services_grid = items
    except Exception:
        services_grid = []

    # --- Inquiry form (reuse your existing Inquiry stack) --------------------
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
        "services_grid": services_grid,
        "year": timezone.now().year,
        "form": form,  # None if InquiryForm couldn't be imported; template can handle gracefully
    }
    return render(request, "home.html", ctx)
