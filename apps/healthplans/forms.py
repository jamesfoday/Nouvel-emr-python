# apps/healthplans/forms.py
from django import forms
from django.contrib.auth import get_user_model
from .models import HealthPlan
User = get_user_model()

class HealthPlanForm(forms.ModelForm):
    # human-friendly currency fields
    price = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0, label="Price")
    deductible = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False, label="Deductible")
    copay = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False, label="Copay")
    oop_max = forms.DecimalField(max_digits=8, decimal_places=2, min_value=0, required=False, label="Out-of-pocket max")

    class Meta:
        model = HealthPlan
        fields = [
            "name","slug","description","interval","price","is_active","sort_order",
            "plan_code","region","includes_telehealth","visits_per_period",
            "deductible","copay","coinsurance_pct","oop_max","stripe_price_id",
        ]

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.instance and self.instance.pk:
            self.fields["price"].initial = (self.instance.price_cents or 0)/100
            self.fields["deductible"].initial = (self.instance.deductible_cents or 0)/100
            self.fields["copay"].initial = (self.instance.copay_cents or 0)/100
            self.fields["oop_max"].initial = (self.instance.oop_max_cents or 0)/100

    def save(self, commit=True):
        obj = super().save(commit=False)
        d = self.cleaned_data
        obj.price_cents = int(round((d.get("price") or 0) * 100))
        obj.deductible_cents = int(round((d.get("deductible") or 0) * 100))
        obj.copay_cents = int(round((d.get("copay") or 0) * 100))
        obj.oop_max_cents = int(round((d.get("oop_max") or 0) * 100))
        if commit: obj.save()
        return obj

class EnrollForm(forms.Form):
    plan_slug = forms.SlugField()


class StaffEnrollForm(forms.Form):
    patient = forms.ModelChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("first_name","last_name","email"),
        label="Patient",
        widget=forms.Select(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"})
    )
    plan = forms.ModelChoiceField(
        queryset=HealthPlan.objects.filter(is_active=True).order_by("sort_order","price_cents"),
        label="Plan",
        widget=forms.Select(attrs={"class": "w-full rounded-xl px-3 py-2 ring-1 ring-gray-200"})
    )    
