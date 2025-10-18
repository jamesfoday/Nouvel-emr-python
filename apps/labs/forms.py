from django import forms
from .models import LabOrder, DiagnosticReport
from .models import LabCatalog
from .models import ExternalLabResult, LabOrder
from django.contrib.auth import get_user_model
User = get_user_model()

# Shared Tailwind classes for glass inputs
BASE_INPUT_CLS = (
    "mt-1 w-full rounded-xl border border-white/40 bg-white/70 px-3 py-2 "
    "outline-none focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100"
)

class LabOrderForm(forms.ModelForm):
    class Meta:
        model = LabOrder
        fields = ["patient", "catalog", "priority", "status", "reason", "notes"]
        widgets = {
            "patient":  forms.Select(attrs={"class": BASE_INPUT_CLS}),
            "catalog":  forms.Select(attrs={"class": BASE_INPUT_CLS}),
            "priority": forms.Select(attrs={"class": BASE_INPUT_CLS}),
            "status":   forms.Select(attrs={"class": BASE_INPUT_CLS}),
            "reason":   forms.Textarea(attrs={
                "class": BASE_INPUT_CLS,
                "rows": 2,
                "placeholder": "Clinical question or reason for test…",
            }),
            "notes":    forms.Textarea(attrs={
                "class": BASE_INPUT_CLS,
                "rows": 3,
                "placeholder": "Any prep, timing, or handling notes…",
            }),
        }

class DiagnosticReportForm(forms.ModelForm):
    class Meta:
        model = DiagnosticReport
        # 'issued_at' is non-editable on the model; no 'summary' field on model.
        fields = ["patient", "performing_lab", "status", "pdf"]
        widgets = {
            "patient":        forms.Select(attrs={"class": BASE_INPUT_CLS}),
            "performing_lab": forms.TextInput(attrs={
                "class": BASE_INPUT_CLS,
                "placeholder": "e.g., Nouvel Diagnostics",
            }),
            "status":         forms.Select(attrs={"class": BASE_INPUT_CLS}),
            "pdf":            forms.ClearableFileInput(attrs={"class": BASE_INPUT_CLS}),
        }


class LabCatalogForm(forms.ModelForm):
    class Meta:
        model = LabCatalog  # fields: code, name, loinc_code, is_panel
        fields = ["code", "name", "loinc_code", "is_panel"]
        widgets = {
            "code":       forms.TextInput(attrs={"class": BASE_INPUT_CLS, "placeholder": "e.g., CBC"}),
            "name":       forms.TextInput(attrs={"class": BASE_INPUT_CLS, "placeholder": "e.g., CBC with differential"}),
            "loinc_code": forms.TextInput(attrs={"class": BASE_INPUT_CLS, "placeholder": "e.g., 57021-8"}),
            "is_panel":   forms.CheckboxInput(attrs={"class": "h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-200"}),
        }


class PatientExternalResultForm(forms.ModelForm):
    class Meta:
        model = ExternalLabResult
        fields = ["order", "clinician_to", "title", "vendor_name", "performed_at", "file", "notes"]
        widgets = {
            "performed_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "input"}),
            "title":        forms.TextInput(attrs={"class": "input", "placeholder": "e.g., Complete Blood Count"}),
            "vendor_name":  forms.TextInput(attrs={"class": "input", "placeholder": "Lab/facility name"}),
            "notes":        forms.Textarea(attrs={"class": "textarea", "rows": 3, "placeholder": "Optional notes"}),
            "order":        forms.Select(attrs={"class": "select"}),
            "clinician_to": forms.Select(attrs={"class": "select"}),
            "file":         forms.ClearableFileInput(attrs={"class": "file-input"}),
        }

    def __init__(self, *args, patient=None, order=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Limit orders to THIS patient
        if patient is not None:
            self.fields["order"].queryset = LabOrder.objects.filter(patient=patient).order_by("-ordered_at")
        else:
            self.fields["order"].queryset = LabOrder.objects.none()

        # Build the allowed clinician set:
        allowed_ids = set()

        if patient is not None:
            # a) single-FK styles commonly used
            for attr in ("primary_clinician_id", "clinician_id", "provider_id", "created_by_id"):
                if getattr(patient, attr, None):
                    allowed_ids.add(getattr(patient, attr))

            # b) many-to-many “care team” style, if present
            care_team = getattr(patient, "care_team", None)
            if care_team is not None:
                try:
                    allowed_ids.update(care_team.values_list("pk", flat=True))
                except Exception:
                    pass

            # c) fallback: any clinician who has ever ordered for this patient
            if not allowed_ids:
                allowed_ids.update(
                    LabOrder.objects.filter(patient=patient).values_list("clinician_id", flat=True).distinct()
                )

        # If the upload is tied to a specific order, force/limit to the order's clinician
        if order is not None:
            if order.clinician_id:
                allowed_ids = {order.clinician_id}
               
                if not self.initial.get("clinician_to"):
                    self.initial["clinician_to"] = order.clinician_id

        # Apply the filtered queryset
        if allowed_ids:
            self.fields["clinician_to"].queryset = User.objects.filter(is_staff=True, pk__in=allowed_ids).order_by(
                "first_name", "last_name"
            )
        else:
            # No clinician relationship found — show none
            self.fields["clinician_to"].queryset = User.objects.none()

        
        self.fields["clinician_to"].required = False
        self.fields["order"].required = False

    def clean(self):
        cleaned = super().clean()
        order = cleaned.get("order")
        clinician = cleaned.get("clinician_to")
        if not order and not clinician:
            raise forms.ValidationError("Select the ordering clinician or attach this to an existing order.")
        if order and not clinician:
            cleaned["clinician_to"] = order.clinician
        return cleaned