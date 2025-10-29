# apps/accounts/forms.py
from django import forms
from .models import ReceptionistProfile

class ReceptionistProfileForm(forms.ModelForm):
    remove_avatar = forms.BooleanField(required=False, label="Remove current avatar")

    class Meta:
        model = ReceptionistProfile
        fields = ["avatar", "title", "phone", "department", "location", "bio"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("remove_avatar"):
            obj.avatar.delete(save=False)
            obj.avatar = None
        if commit:
            obj.save()
        return obj
