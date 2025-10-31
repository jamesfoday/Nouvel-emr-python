# apps/services/views.py
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Q
from django.forms import modelform_factory
from django.shortcuts import get_object_or_404, redirect, render, resolve_url
from django.utils.text import slugify
from django import forms

from .forms import ServiceSectionFormSet
from .models import Service, ServiceCategory


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


# Centralized public queryset: only public/active if present, newest first.
def _public_qs():
    qs = Service.objects.all().prefetch_related("sections", "categories")
    if _has_field(Service, "is_active"):
        qs = qs.filter(is_active=True)
    if _has_field(Service, "is_public"):
        qs = qs.filter(is_public=True)
    if _has_field(Service, "created_at"):
        qs = qs.order_by("-created_at", "title")
    else:
        qs = qs.order_by("title")
    return qs


def recent_services(limit=6):
    """Return the latest N services for the homepage grid."""
    return _public_qs()[:limit]


def _service_form():
    """
    Build a ModelForm for Service that includes all editable concrete fields,
    and force 'categories' to render as CheckboxSelectMultiple so selections bind.
    """
    include_names = []
    for f in Service._meta.get_fields():
        if getattr(f, "auto_created", False):
            continue  # skip reverse relations
        if getattr(f, "editable", False):
            include_names.append(f.name)

    widgets = {}

    # Force categories -> checkboxes if the field exists and is M2M
    try:
        field = Service._meta.get_field("categories")
        if getattr(field, "many_to_many", False):
            widgets["categories"] = forms.CheckboxSelectMultiple(
                attrs={"class": "grid grid-cols-2 gap-2 md:grid-cols-3"}
            )
    except Exception:
        pass

    # Nice input styling for title (optional)
    if "title" in include_names:
        widgets["title"] = forms.TextInput(
            attrs={
                "placeholder": "Service title",
                "class": "w-full rounded-xl bg-white px-3 py-3 ring-1 ring-gray-200 focus:ring-emerald-500",
            }
        )

    return modelform_factory(Service, fields=(include_names or "__all__"), widgets=widgets)


# ----------------------------- PUBLIC PAGES ------------------------------
def services_public_list(request):
    """
    Public 'See all services' page with optional search (?q=) and
    optional category filter (?cat=<category-slug>).
    """
    q = (request.GET.get("q") or "").strip()
    cat_slug = (request.GET.get("cat") or "").strip()

    qs = _public_qs()

    # category filter
    active_category = None
    if cat_slug:
        active_category = ServiceCategory.objects.filter(slug=cat_slug, is_public=True).first()
        if active_category:
            qs = qs.filter(categories=active_category)

    # search filter
    if q:
        q_obj = Q(title__icontains=q)
        if _has_field(Service, "summary"):
            q_obj |= Q(summary__icontains=q)
        if _has_field(Service, "description"):
            q_obj |= Q(description__icontains=q)
        # also search within sections
        q_obj |= Q(sections__subtitle__icontains=q) | Q(sections__description__icontains=q)
        qs = qs.filter(q_obj).distinct()

    categories = ServiceCategory.objects.filter(is_public=True).order_by("order", "name")

    return render(
        request,
        "services/public_list.html",
        {
            "services": qs,
            "q": q,
            "categories": categories,
            "active_category": active_category,
        },
    )


# /services/browse/?q=... (homepage search target)
def service_catalog(request):
    """
    Public, anonymous-friendly catalog view used by the homepage search.
    Supports ?q= and optional ?cat= like the public_list to keep UX aligned.
    """
    q = (request.GET.get("q") or "").strip()
    cat_slug = (request.GET.get("cat") or "").strip()

    qs = _public_qs()

    active_category = None
    if cat_slug:
        active_category = ServiceCategory.objects.filter(slug=cat_slug, is_public=True).first()
        if active_category:
            qs = qs.filter(categories=active_category)

    if q:
        q_obj = Q(title__icontains=q)
        if _has_field(Service, "summary"):
            q_obj |= Q(summary__icontains=q)
        if _has_field(Service, "description"):
            q_obj |= Q(description__icontains=q)
        q_obj |= Q(sections__subtitle__icontains=q) | Q(sections__description__icontains=q)
        qs = qs.filter(q_obj).distinct()

    categories = ServiceCategory.objects.filter(is_public=True).order_by("order", "name")

    return render(
        request,
        "services/catalog.html",
        {
            "services": qs,
            "q": q,
            "categories": categories,
            "active_category": active_category,
        },
    )


def service_detail(request, slug):
    """
    Public detail page for a service.
    """
    service = (
        get_object_or_404(Service.objects.prefetch_related("sections", "categories"), slug=slug)
        if _has_field(Service, "slug")
        else get_object_or_404(Service.objects.prefetch_related("sections", "categories"), pk=slug)
    )
    return render(request, "services/service_detail.html", {"service": service})


# ----------------------------- STAFF PAGES -----------------------------------
@login_required
@user_passes_test(is_staff_or_superuser)
def service_list(request):
    """
    Staff-only index with actions (create/edit/delete).
    """
    q = (request.GET.get("q") or "").strip()
    qs = Service.objects.all().prefetch_related("categories", "sections")

    if q:
        q_obj = Q(title__icontains=q)
        if _has_field(Service, "summary"):
            q_obj |= Q(summary__icontains=q)
        if _has_field(Service, "description"):
            q_obj |= Q(description__icontains=q)
        q_obj |= Q(sections__subtitle__icontains=q) | Q(sections__description__icontains=q)
        qs = qs.filter(q_obj).distinct()

    if _has_field(Service, "created_at"):
        qs = qs.order_by("-created_at")
    else:
        qs = qs.order_by("title")

    return render(request, "services/service_list.html", {"services": qs, "q": q})


@login_required
@user_passes_test(is_staff_or_superuser)
def service_create(request):
    Form = _service_form()

    if request.method == "POST":
        form = Form(request.POST, request.FILES)
        formset = ServiceSectionFormSet(request.POST, request.FILES, prefix="sections")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                obj = form.save(commit=False)

                # Auto slug if missing
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

                # tie sections to this service and save
                formset.instance = obj
                formset.save()

            messages.success(request, "Service created.")
            return redirect(resolve_url("services:list"))
    else:
        form = Form()
        formset = ServiceSectionFormSet(prefix="sections")

    return render(
        request,
        "services/service_form.html",
        {"form": form, "formset": formset, "is_create": True},
    )


@login_required
@user_passes_test(is_staff_or_superuser)
def service_update(request, slug):
    instance = (
        get_object_or_404(Service, slug=slug)
        if _has_field(Service, "slug")
        else get_object_or_404(Service, pk=slug)
    )
    Form = _service_form()

    if request.method == "POST":
        form = Form(request.POST, request.FILES, instance=instance)
        formset = ServiceSectionFormSet(
            request.POST, request.FILES, instance=instance, prefix="sections"
        )
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
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

                formset.instance = obj
                formset.save()

            messages.success(request, "Service updated.")
            return redirect(resolve_url("services:list"))
    else:
        form = Form(instance=instance)
        formset = ServiceSectionFormSet(instance=instance, prefix="sections")

    return render(
        request,
        "services/service_form.html",
        {"form": form, "formset": formset, "is_create": False, "instance": instance},
    )


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

    return render(request, "services/service_confirm_delete.html", {"service": instance})
