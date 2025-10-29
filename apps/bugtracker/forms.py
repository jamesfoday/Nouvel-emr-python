from django import forms
from .models import BugReport

class BugReportCreateForm(forms.ModelForm):
    class Meta:
        model = BugReport
        fields = ["title", "description", "page_url", "screenshot", "severity"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

class BugReportAdminForm(forms.ModelForm):
    class Meta:
        model = BugReport
        fields = ["status", "assigned_to", "resolution_note", "severity"]
        widgets = {
            "resolution_note": forms.Textarea(attrs={"rows": 4}),
        }
