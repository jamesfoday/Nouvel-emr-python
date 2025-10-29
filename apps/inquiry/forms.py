
from django import forms
from .models import Inquiry


class InquiryForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ["name", "email", "message"]
        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Name", "class": "w-full rounded-xl ring-1 ring-gray-300 px-4 py-2"
            }),
            "email": forms.EmailInput(attrs={
                "placeholder": "Email", "class": "w-full rounded-xl ring-1 ring-gray-300 px-4 py-2"
            }),
            "message": forms.Textarea(attrs={
                "placeholder": "Message", "rows": 6,
                "class": "w-full rounded-xl ring-1 ring-gray-300 px-4 py-2"
            }),
        }


class InquiryUpdateForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = ["status", "staff_note"]
        widgets = {
            "status": forms.Select(attrs={"class": "w-full rounded-xl ring-1 ring-gray-300 px-3 py-2"}),
            "staff_note": forms.Textarea(attrs={
                "rows": 6, "class": "w-full rounded-xl ring-1 ring-gray-300 px-3 py-2"
            }),
        }
