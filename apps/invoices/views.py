# apps/invoices/views.py
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction, models
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Invoice
from .forms import InvoiceForm, InvoiceItemFormSet

FORMSET_PREFIX = "items"  # must match template/JS ("id_items-TOTAL_FORMS")


@login_required
def invoice_list(request):
    q = (request.GET.get("q") or "").strip()
    invoices = (
        Invoice.objects.select_related("customer")
        .prefetch_related("items")
        .order_by("-created_at")
    )
    if q:
        invoices = invoices.filter(
            models.Q(number__icontains=q)
            | models.Q(customer__email__icontains=q)
            | models.Q(customer__given_name__icontains=q)
            | models.Q(customer__family_name__icontains=q)
            | models.Q(customer__external_id__icontains=q)
        )
    return render(request, "invoices/list.html", {"invoices": invoices, "q": q})


@login_required
@transaction.atomic
def invoice_create(request):
    if request.method == "POST":
        form = InvoiceForm(request.POST)
        formset = InvoiceItemFormSet(request.POST, prefix=FORMSET_PREFIX)
        if form.is_valid() and formset.is_valid():
            invoice = form.save()
            formset.instance = invoice
            formset.save()
            invoice.compute_totals()
            invoice.save(update_fields=["subtotal", "tax_amount", "total"])
            messages.success(request, "Invoice created.")
            return redirect("invoices:detail", pk=invoice.pk)
    else:
        form = InvoiceForm()
        # Seed exactly ONE empty row on GET (since extra=0 in formset)
        formset = InvoiceItemFormSet(prefix=FORMSET_PREFIX, initial=[{}])

    return render(
        request,
        "invoices/form.html",
        {"form": form, "formset": formset, "mode": "create"},
    )


@login_required
@transaction.atomic
def invoice_update(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == "POST":
        form = InvoiceForm(request.POST, instance=invoice)
        formset = InvoiceItemFormSet(request.POST, instance=invoice, prefix=FORMSET_PREFIX)
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            invoice.compute_totals()
            invoice.save(update_fields=["subtotal", "tax_amount", "total"])
            messages.success(request, "Invoice updated.")
            return redirect("invoices:detail", pk=invoice.pk)
    else:
        form = InvoiceForm(instance=invoice)
        formset = InvoiceItemFormSet(instance=invoice, prefix=FORMSET_PREFIX)

    return render(
        request,
        "invoices/form.html",
        {"form": form, "formset": formset, "mode": "edit", "invoice": invoice},
    )


@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer").prefetch_related("items"),
        pk=pk,
    )
    return render(request, "invoices/detail.html", {"invoice": invoice})


@login_required
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == "POST":
        invoice.delete()
        messages.success(request, "Invoice deleted.")
        return redirect("invoices:list")
    return render(request, "invoices/confirm_delete.html", {"invoice": invoice})


@login_required
def invoice_pdf(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related("customer").prefetch_related("items"),
        pk=pk,
    )

    # Render HTML and inject <base> for relative URLs
    html = render(request, "invoices/pdf_tailwind.html", {"invoice": invoice}).content.decode("utf-8")
    base_href = request.build_absolute_uri("/")
    if "</head>" in html:
        html = html.replace("</head>", f'<base href="{base_href}"></base></head>')
    else:
        html = f'<head><base href="{base_href}"></base></head>' + html

    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        messages.error(
            request,
            "PDF generation isn't available. Install Playwright:\n"
            "pip install playwright && python -m playwright install chromium"
        )
        return redirect("invoices:detail", pk=pk)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=True)
        except Exception:
            browser = p.chromium.launch(headless=True)

        page = browser.new_page()
        page.set_content(html, wait_until="domcontentloaded")
        # Wait until Tailwind runtime is available and styles are applied
        page.wait_for_function("typeof tailwind !== 'undefined'")
        page.wait_for_load_state("networkidle")
        page.emulate_media(media="print")

        pdf_bytes = page.pdf(
            format="A4",
            margin={"top": "22mm", "right": "22mm", "bottom": "22mm", "left": "22mm"},
            print_background=True,
        )
        browser.close()

    filename = f"{invoice.number or f'invoice-{invoice.pk}'}.pdf"
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp