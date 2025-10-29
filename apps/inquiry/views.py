from django.shortcuts import render
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import get_object_or_404, redirect, render
from django.core.mail import send_mail
from django.conf import settings
from django.core.paginator import Paginator

from .forms import InquiryForm, InquiryUpdateForm
from .models import Inquiry


def inquiry_create(request):
    """Public form where anyone can send an inquiry."""
    if request.method == "POST":
        form = InquiryForm(request.POST)
        if form.is_valid():
            inquiry = form.save()
            # Optional: notify team by email
            try:
                send_mail(
                    subject=f"New Inquiry from {inquiry.name}",
                    message=inquiry.message,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                    recipient_list=getattr(settings, "INQUIRY_NOTIFY_TO", []),
                    fail_silently=True,
                )
            except Exception:
                pass
            messages.success(request, "Thanks! Your message has been sent.")
            return redirect("inquiry:thanks")
    else:
        form = InquiryForm()
    return render(request, "inquiry/form.html", {"form": form})


def inquiry_thanks(request):
    return render(request, "inquiry/thanks.html")


@staff_member_required
def inquiry_list(request):
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Inquiry.objects.all()
    if q:
        qs = qs.filter(message__icontains=q) | qs.filter(name__icontains=q) | qs.filter(email__icontains=q)
    if status:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 20)
    page = request.GET.get("page")
    inquiries = paginator.get_page(page)

    return render(request, "inquiry/list.html", {"inquiries": inquiries, "q": q, "status": status})


@staff_member_required
def inquiry_detail(request, pk):
    inquiry = get_object_or_404(Inquiry, pk=pk)
    if request.method == "POST":
        form = InquiryUpdateForm(request.POST, instance=inquiry)
        if form.is_valid():
            form.save()
            messages.success(request, "Inquiry updated.")
            return redirect("inquiry:detail", pk=pk)
    else:
        form = InquiryUpdateForm(instance=inquiry)
    return render(request, "inquiry/detail.html", {"inquiry": inquiry, "form": form})
