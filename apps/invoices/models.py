# invoices/models.py
from django.db import models
from django.utils import timezone


class Invoice(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("sent", "Sent"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("void", "Void"),
    ]

    number = models.CharField(max_length=20, unique=True, blank=True)

    # 👇 Now points to your Patient model instead of User
    customer = models.ForeignKey(
        "patients.Patient", on_delete=models.PROTECT, related_name="invoices"
    )

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="draft")
    currency = models.CharField(max_length=8, default="EUR")
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percent

    issued_at = models.DateField(default=timezone.now)
    due_at = models.DateField(null=True, blank=True)

    note = models.TextField(blank=True)

    # cached totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.number or f"Invoice {self.pk}"

    def compute_totals(self):
        """Recalculate subtotal/tax/total from line items."""
        from decimal import Decimal

        items_total = sum(
            (item.qty * item.unit_price for item in self.items.all()),
            start=Decimal("0"),
        )
        self.subtotal = items_total
        self.tax_amount = (items_total * (self.tax_rate or 0) / 100)
        self.total = items_total + self.tax_amount

    def save(self, *args, **kwargs):
        """Assign an invoice number on first save, e.g. INV-202510-0001."""
        creating = self._state.adding and not self.number
        super().save(*args, **kwargs)
        if creating:
            ym = self.issued_at.strftime("%Y%m")
            self.number = f"INV-{ym}-{self.pk:04d}"
            super().save(update_fields=["number"])


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    qty = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    @property
    def line_total(self):
        return self.qty * self.unit_price

    def __str__(self) -> str:
        return f"{self.description} ({self.qty} x {self.unit_price})"
