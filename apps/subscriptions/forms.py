from django import forms
from .models import Plan, PlanInterval

class SubscribeForm(forms.Form):
    plan_slug = forms.SlugField()

    def clean_plan_slug(self):
        slug = self.cleaned_data["plan_slug"]
        try:
            plan = Plan.objects.get(slug=slug, is_active=True)
        except Plan.DoesNotExist:
            raise forms.ValidationError("Plan not available.")
        self.plan = plan
        return slug






class PlanForm(forms.ModelForm):
    # Expose a decimal "price" in currency, map to price_cents internally
    price = forms.DecimalField(
        max_digits=8, decimal_places=2, min_value=0, label="Price",
        help_text="Amount in your billing currency (e.g., 9.99)."
    )

    class Meta:
        model = Plan
        fields = [
            "name", "slug", "description",
            "interval", "price", "is_active", "sort_order",
            "max_patients", "max_staff", "storage_mb",
            "stripe_price_id",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "slug": forms.TextInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "description": forms.Textarea(attrs={"rows": 5, "class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "interval": forms.Select(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "is_active": forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
            "sort_order": forms.NumberInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "max_patients": forms.NumberInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "max_staff": forms.NumberInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "storage_mb": forms.NumberInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"}),
            "stripe_price_id": forms.TextInput(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200", "placeholder": "price_123... (optional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize price from price_cents
        if self.instance and self.instance.pk:
            self.fields["price"].initial = (self.instance.price_cents or 0) / 100

    def save(self, commit=True):
        obj = super().save(commit=False)
        price = self.cleaned_data.get("price") or 0
        obj.price_cents = int(round(price * 100))
        if commit:
            obj.save()
        return obj
