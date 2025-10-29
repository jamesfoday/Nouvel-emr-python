from django.shortcuts import render
from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db.models import Q

from .models import BugReport
from .forms import BugReportCreateForm, BugReportAdminForm

def is_superuser(u):
    return bool(u and u.is_authenticated and u.is_superuser)

def is_staff(u):
    return bool(u and u.is_authenticated and u.is_staff)

@login_required
@user_passes_test(is_staff)
def report_create(request):
    if request.method == "POST":
        form = BugReportCreateForm(request.POST, request.FILES)
        if form.is_valid():
            bug = form.save(commit=False)
            bug.reporter = request.user
            bug.save()
            messages.success(request, "Thanks! Your bug report was submitted.")
            return redirect("bugtracker:list")
    else:
        form = BugReportCreateForm()
    return render(request, "bugtracker/form.html", {"form": form, "mode": "create"})

@login_required
def report_list(request):
    """
    - Superusers: see all.
    - Staff: see their own reports and items assigned to them.
    """
    q = (request.GET.get("q") or "").strip()
    base = BugReport.objects.select_related("reporter", "assigned_to")
    if request.user.is_superuser:
        qs = base
    else:
        qs = base.filter(Q(reporter=request.user) | Q(assigned_to=request.user))

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))

    return render(request, "bugtracker/list.html", {"bugs": qs, "q": q})

@login_required
def report_detail(request, pk: int):
    bug = get_object_or_404(BugReport.objects.select_related("reporter", "assigned_to"), pk=pk)

    # Access:
    # - Superuser: always
    # - Staff: only if reporter or assigned_to
    if not request.user.is_superuser and not (bug.reporter_id == request.user.id or bug.assigned_to_id == request.user.id):
        messages.error(request, "You do not have access to this bug.")
        return redirect("bugtracker:list")

    # Only superusers can update triage fields
    admin_form = None
    if request.user.is_superuser:
        if request.method == "POST":
            admin_form = BugReportAdminForm(request.POST, instance=bug)
            if admin_form.is_valid():
                admin_form.save()
                messages.success(request, "Bug updated.")
                return redirect("bugtracker:detail", pk=bug.pk)
        else:
            admin_form = BugReportAdminForm(instance=bug)

    return render(request, "bugtracker/detail.html", {"bug": bug, "admin_form": admin_form})
