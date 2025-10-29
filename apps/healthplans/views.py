# apps/healthplans/views.py

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .models import HealthPlan, Enrollment, EnrollmentStatus, PlanInterval
from .forms import HealthPlanForm, StaffEnrollForm
from django.db.models import ProtectedError


# =============================================================================
# Staff console
# =============================================================================

@staff_member_required
def staff_plan_list(request):
    plans = HealthPlan.objects.all().order_by("sort_order", "price_cents")

    q = request.GET.get("q", "").strip()
    enrollments_qs = Enrollment.objects.select_related("user", "plan").order_by("-created_at")
    if q:
        from django.db.models import Q
        enrollments_qs = enrollments_qs.filter(
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q)
        )

    
    enrollments = enrollments_qs[:50]
    context = {
        "plans": plans,
        "enrollments": enrollments,
        "q": q,
        "enrollments_has_more": enrollments_qs.count() > 50,
        "next_page": 2,  
    }
    return render(request, "healthplans/staff_plan_list.html", context)


@staff_member_required
def plan_create(request):
    """Create a new health plan."""
    form = HealthPlanForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        plan = form.save()
        messages.success(request, f'Health plan “{plan.name}” created.')
        return redirect("healthplans:staff_plans")
    return render(request, "healthplans/plan_create.html", {"form": form})


@staff_member_required
def plan_update(request, slug):
    """Edit an existing health plan."""
    plan = get_object_or_404(HealthPlan, slug=slug)
    form = HealthPlanForm(request.POST or None, instance=plan)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Plan updated.")
        return redirect("healthplans:staff_plans")
    return render(request, "healthplans/plan_create.html", {"form": form, "editing": True})


@staff_member_required
def plan_delete(request, slug):
    plan = get_object_or_404(HealthPlan, slug=slug)
    if request.method == "POST":
        try:
            plan.delete()
            messages.success(request, f'Plan “{plan.name}” deleted.')
        except ProtectedError:
            plan.is_active = False
            plan.save(update_fields=["is_active"])
            messages.warning(
                request,
                f'Plan “{plan.name}” has enrollments and was archived (disabled) instead of deleted.'
            )
        return redirect("healthplans:staff_plans")
    return render(request, "healthplans/confirm_delete.html", {"plan": plan})

@staff_member_required
def staff_enroll_patient(request):
    """Staff enrolls a chosen patient into a plan immediately (no Stripe)."""
    form = StaffEnrollForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.cleaned_data["patient"]
        plan = form.cleaned_data["plan"]

        now = timezone.now()
        length_days = 30 if plan.interval == PlanInterval.MONTH else 365
        end = now + timezone.timedelta(days=length_days)

        # Soft-switch any current active enrollment
        current = Enrollment.objects.filter(
            user=user,
            status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.TRIALING],
        ).first()
        if current:
            current.cancel_at_period_end = True
            current.save(update_fields=["cancel_at_period_end"])

        Enrollment.objects.create(
            user=user,
            plan=plan,
            status=EnrollmentStatus.ACTIVE,
            start_at=now,
            current_period_start=now,
            current_period_end=end,
        )
        display = user.get_full_name() or user.email or f"User #{user.pk}"
        messages.success(request, f"{display} enrolled in {plan.name}.")
        return redirect("healthplans:staff_plans")

    return render(request, "healthplans/staff_enroll_patient.html", {"form": form})


# =============================================================================
# Patient-facing
# =============================================================================

def user_plan_list(request):
    """
    Public list of active plans.
    If the user is authenticated, we also show their current enrollment state.
    """
    plans = HealthPlan.objects.filter(is_active=True).order_by("sort_order", "price_cents")
    enrollment = None
    if request.user.is_authenticated:
        enrollment = Enrollment.objects.filter(user=request.user).order_by("-created_at").first()
    return render(request, "healthplans/plan_list.html", {"plans": plans, "enrollment": enrollment})


@login_required
def checkout_modal(request, slug):
    """
    Returns the modal inner HTML for a given plan (loaded via fetch/HTMX).
    Stripe-free; just shows plan info and an 'Enroll now' button.
    """
    plan = get_object_or_404(HealthPlan, slug=slug, is_active=True)
    return render(request, "healthplans/_checkout_modal_inner.html", {"plan": plan})


@login_required
def checkout_start(request):
    """
    Stripe-free checkout: immediately enroll the current user in the plan.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("POST required")

    slug = request.POST.get("plan_slug")
    plan = get_object_or_404(HealthPlan, slug=slug, is_active=True)

    now = timezone.now()
    length_days = 30 if plan.interval == PlanInterval.MONTH else 365
    end = now + timezone.timedelta(days=length_days)

    # Soft-switch any current active enrollment
    current = Enrollment.objects.filter(
        user=request.user,
        status__in=[EnrollmentStatus.ACTIVE, EnrollmentStatus.TRIALING],
    ).first()
    if current:
        current.cancel_at_period_end = True
        current.save(update_fields=["cancel_at_period_end"])

    Enrollment.objects.create(
        user=request.user,
        plan=plan,
        status=EnrollmentStatus.ACTIVE,
        start_at=now,
        current_period_start=now,
        current_period_end=end,
    )

    messages.success(request, f"You’re enrolled in {plan.name}.")
    return redirect("healthplans:plans")


@login_required
def cancel(request):
    """User requests to cancel at period end."""
    if request.method == "POST":
        en = Enrollment.objects.filter(user=request.user).order_by("-created_at").first()
        if en and en.is_active():
            en.cancel_at_period_end = True
            en.save(update_fields=["cancel_at_period_end"])
            messages.success(request, "Your plan will end at the close of the current period.")
    
    return redirect("healthplans:staff_plans")


@login_required
def resume(request):
    """User resumes a previously cancel-at-period-end enrollment."""
    if request.method == "POST":
        en = Enrollment.objects.filter(user=request.user).order_by("-created_at").first()
        if en and en.cancel_at_period_end and en.is_active():
            en.cancel_at_period_end = False
            en.save(update_fields=["cancel_at_period_end"])
            messages.success(request, "Your plan will continue.")
    return redirect("healthplans:plans")



@staff_member_required
def plan_archive(request, slug):
    plan = get_object_or_404(HealthPlan, slug=slug)
    if request.method == "POST":
        plan.is_active = not plan.is_active
        plan.save(update_fields=["is_active"])
        messages.success(request, f'Plan “{plan.name}” ' + ('unarchived.' if plan.is_active else 'archived.'))
    return redirect("healthplans:staff_plans")



@staff_member_required
def staff_enrollment_cancel(request, enrollment_id):
    if request.method == "POST":
        en = get_object_or_404(Enrollment, pk=enrollment_id)
        if en.status in (EnrollmentStatus.ACTIVE, EnrollmentStatus.TRIALING):
            en.cancel_at_period_end = True
            en.save(update_fields=["cancel_at_period_end"])
            messages.success(request, f"{en.user} will be canceled at period end.")
    return redirect("healthplans:staff_plans")

@staff_member_required
def staff_enrollment_resume(request, enrollment_id):
    if request.method == "POST":
        en = get_object_or_404(Enrollment, pk=enrollment_id)
        if en.status in (EnrollmentStatus.ACTIVE, EnrollmentStatus.TRIALING) and en.cancel_at_period_end:
            en.cancel_at_period_end = False
            en.save(update_fields=["cancel_at_period_end"])
            messages.success(request, f"{en.user}'s plan will continue.")
    return redirect("healthplans:staff_plans")
