from django.shortcuts import render
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .models import Plan, Subscription, SubscriptionStatus, PlanInterval
from .forms import SubscribeForm

from django.contrib.admin.views.decorators import staff_member_required
from django.urls import reverse
from .forms import PlanForm

@login_required
def plan_list(request):
    plans = Plan.objects.filter(is_active=True).order_by("sort_order", "price_cents")
    # current sub (if any)
    sub = Subscription.objects.filter(user=request.user).order_by("-created_at").first()
    return render(request, "subscriptions/plan_list.html", {"plans": plans, "sub": sub})

@login_required
def plan_detail(request, slug):
    plan = get_object_or_404(Plan, slug=slug, is_active=True)
    sub = Subscription.objects.filter(user=request.user).order_by("-created_at").first()
    return render(request, "subscriptions/plan_detail.html", {"plan": plan, "sub": sub})

@login_required
def subscribe(request):
    if request.method != "POST":
        return redirect("subscriptions:plans")

    form = SubscribeForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Invalid plan.")
        return redirect("subscriptions:plans")

    plan = form.plan
    now = timezone.now()
    # End bound of first period
    if plan.interval == PlanInterval.MONTH:
        end = now + timezone.timedelta(days=30)
    else:
        end = now + timezone.timedelta(days=365)

    # cancel any existing active sub at period end (soft switch)
    existing = Subscription.objects.filter(user=request.user, status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]).first()
    if existing:
        existing.cancel_at_period_end = True
        existing.status = SubscriptionStatus.ACTIVE  # stays active until end
        existing.save(update_fields=["cancel_at_period_end", "status"])

    sub = Subscription.objects.create(
        user=request.user,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        start_at=now,
        current_period_start=now,
        current_period_end=end,
    )
    messages.success(request, f"Subscribed to {plan.name}.")
    return redirect("subscriptions:plans")

@login_required
def cancel(request):
    if request.method != "POST":
        return redirect("subscriptions:plans")
    sub = Subscription.objects.filter(user=request.user).order_by("-created_at").first()
    if not sub or not sub.is_active():
        messages.info(request, "No active subscription to cancel.")
        return redirect("subscriptions:plans")
    sub.cancel_at_period_end = True
    sub.save(update_fields=["cancel_at_period_end"])
    messages.success(request, "Your subscription will end at the end of the current period.")
    return redirect("subscriptions:plans")

@login_required
def resume(request):
    if request.method != "POST":
        return redirect("subscriptions:plans")
    sub = Subscription.objects.filter(user=request.user).order_by("-created_at").first()
    if not sub:
        messages.info(request, "No subscription found.")
        return redirect("subscriptions:plans")
    if sub.cancel_at_period_end and sub.is_active():
        sub.cancel_at_period_end = False
        sub.save(update_fields=["cancel_at_period_end"])
        messages.success(request, "Cancellation undone. Your subscription will continue.")
    else:
        messages.info(request, "Nothing to resume.")
    return redirect("subscriptions:plans")




@staff_member_required
def plan_create(request):
    if request.method == "POST":
        form = PlanForm(request.POST)
        if form.is_valid():
            plan = form.save()
            messages.success(request, f"Plan “{plan.name}” created.")
            return redirect("subscriptions:plans")
    else:
        form = PlanForm()
    return render(request, "subscriptions/plan_create.html", {"form": form})