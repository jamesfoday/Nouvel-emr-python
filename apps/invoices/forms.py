from django import forms
from django.forms import inlineformset_factory
from apps.patients.models import Patient
from .models import Invoice, InvoiceItem


class InvoiceForm(forms.ModelForm):
    # HTML5 calendar pickers
    issued_at = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    due_at = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Invoice
        fields = ["customer", "status", "currency", "tax_rate", "issued_at", "due_at", "note"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Only active, non-merged patients (your Patient manager)
        self.fields["customer"].queryset = (
            Patient.objects.active().order_by("family_name", "given_name", "id")
        )
        self.fields["customer"].label_from_instance = lambda p: p.full_name
        self.fields["customer"].empty_label = "---------- Select patient ----------"

        # UX tweak
        self.fields["tax_rate"].widget.attrs.update({"step": "0.01", "min": "0"})


# Important: no server-side blank added; JS will add exactly one per click.
InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    fields=["description", "qty", "unit_price"],
    extra=1,            # <- prevents Django from rendering an extra blank row
    can_delete=True,
    min_num=0,
    validate_min=False,
)
