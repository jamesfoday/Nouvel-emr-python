# apps/services/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.utils.text import slugify

from .models import Service


# ----------------------------- helpers ---------------------------------
def is_staff_or_superuser(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def _has_field(model_cls, field_name: str) -> bool:
    try:
        model_cls._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _unique_slug(base: str) -> str:
    """
    Generate a unique slug for Service from a base string.
    Only used if the Service model has a 'slug' field.
    """
    s = slugify(base) or "item"
    if not Service.objects.filter(slug=s).exists():
        return s
    i = 2
    while True:
        cand = f"{s}-{i}"
        if not Service.objects.filter(slug=cand).exists():
            return cand
        i += 1


def _service_form():
    """
    Build a ModelForm for Service that includes all editable concrete fields.
    Works even if your model has custom fields.
    """
    # Pick editable, concrete (no reverse relations / m2o auto), keep M2M if editable.
    include_names = []
    for f in Service._meta.get_fields():
        # Skip auto created reverse relations etc.
        if getattr(f, "auto_created", False):
            continue
        # Concrete fields or M2M are okay if editable
        if getattr(f, "editable", False):
            # Some relation fields can be non-concrete but editable; allow.
            include_names.append(f.name)

    # Fallback: if nothing found, let modelform_factory decide (rare)
    if not include_names:
        return modelform_factory(Service, fields="__all__")

    return modelform_factory(Service, fields=include_names)


# ----------------------------- PUBLIC ----------------------------------
# /services/browse/?q=...
def service_catalog(request):
    """
    Public, anonymous-friendly catalog view used by the homepage search.
    """
    q = (request.GET.get("q") or "").strip()

    qs = Service.objects.all()

    # Prefer active/public rows if those fields exist
    if _has_field(Service, "is_active"):
        qs = qs.filter(is_active=True)
    if _has_field(Service, "is_public"):
        qs = qs.filter(is_public=True)

    if q:
        q_obj = Q(title__icontains=q)
        if _has_field(Service, "summary"):
            q_obj |= Q(summary__icontains=q)
        if _has_field(Service, "description"):
            q_obj |= Q(description__icontains=q)
        qs = qs.filter(q_obj)

    if _has_field(Service, "created_at"):
        qs = qs.order_by("-created_at")
    else:
        qs = qs.order_by("title")

    # Use a public-facing template; if you prefer, you can reuse your grid template instead.
    return render(request, "services/catalog.html", {"services": qs, "q": q})


def service_detail(request, slug):
    """
    Public detail page for a service.
    """
    service = get_object_or_404(Service, slug=slug) if _has_field(Service, "slug") else get_object_or_404(Service, pk=slug)
    return render(request, "services/service_detail.html", {"service": service})


# ----------------------------- STAFF -----------------------------------
@login_required
@user_passes_test(is_staff_or_superuser)
def service_list(request):
    """
    Staff-only index with actions (create/edit/delete).
    """
    q = (request.GET.get("q") or "").strip()
    qs = Service.objects.all()

    if q:
        q_obj = Q(title__icontains=q)
        if _has_field(Service, "summary"):
            q_obj |= Q(summary__icontains=q)
        if _has_field(Service, "description"):
            q_obj |= Q(description__icontains=q)
        qs = qs.filter(q_obj)

    if _has_field(Service, "created_at"):
        qs = qs.order_by("-created_at")
    else:
        qs = qs.order_by("title")

    return render(request, "services/service_list.html", {"services": qs, "q": q})


@login_required
@user_passes_test(is_staff_or_superuser)
def service_create(request):
    """
    Staff-only create view. Auto-fills 'slug' from 'title' if available and empty.
    """
    Form = _service_form()

    if request.method == "POST":
        form = Form(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)

            # Auto slug if model has 'slug' field and it's blank
            if _has_field(Service, "slug"):
                cur_slug = getattr(obj, "slug", "") or ""
                # Prefer title for slug source if present, else any text-like field
                if not cur_slug:
                    if _has_field(Service, "title") and getattr(obj, "title", None):
                        obj.slug = _unique_slug(getattr(obj, "title"))
                    else:
                        obj.slug = _unique_slug(str(obj))

            obj.save()
            # Save M2M if present
            if hasattr(form, "save_m2m"):
                form.save_m2m()

            messages.success(request, "Service created.")
            return redirect(resolve_url("services:list"))
    else:
        form = Form()

    return render(request, "services/service_form.html", {"form": form, "is_create": True})


@login_required
@user_passes_test(is_staff_or_superuser)
def service_update(request, slug):
    """
    Staff-only update view. If slug field exists and is blank, regenerate from title.
    """
    instance = (
        get_object_or_404(Service, slug=slug)
        if _has_field(Service, "slug")
        else get_object_or_404(Service, pk=slug)
    )
    Form = _service_form()

    if request.method == "POST":
        form = Form(request.POST, request.FILES, instance=instance)
        if form.is_valid():
            obj = form.save(commit=False)

            if _has_field(Service, "slug"):
                cur_slug = getattr(obj, "slug", "") or ""
                if not cur_slug:
                    if _has_field(Service, "title") and getattr(obj, "title", None):
                        obj.slug = _unique_slug(getattr(obj, "title"))
                    else:
                        obj.slug = _unique_slug(str(obj))

            obj.save()
            if hasattr(form, "save_m2m"):
                form.save_m2m()

            messages.success(request, "Service updated.")
            return redirect(resolve_url("services:list"))
    else:
        form = Form(instance=instance)

    return render(request, "services/service_form.html", {"form": form, "is_create": False, "instance": instance})


@login_required
@user_passes_test(is_staff_or_superuser)
def service_delete(request, slug):
    """
    Staff-only delete view. GET shows a confirmation page; POST deletes.
    """
    instance = (
        get_object_or_404(Service, slug=slug)
        if _has_field(Service, "slug")
        else get_object_or_404(Service, pk=slug)
    )

    if request.method == "POST":
        title = getattr(instance, "title", str(instance))
        instance.delete()
        messages.success(request, f"Service “{title}” deleted.")
        return redirect(resolve_url("services:list"))

    # Render a simple confirmation template (create it if missing)
    return render(request, "services/service_confirm_delete.html", {"service": instance})
