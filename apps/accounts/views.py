# apps/accounts/views.py
from django import forms
from django.contrib.auth import login
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import FormView

from .models import User, Invite
from apps.rbac.models import RoleBinding
from ..audit.utils import log_event  # sibling import; keeps editors and runtime happy


class AcceptInviteForm(forms.Form):
    username = forms.CharField(max_length=150)
    display_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        #  refuse duplicate usernames upfront to avoid integrity noise later.
        uname = self.cleaned_data["username"]
        if User.objects.filter(username=uname).exists():
            raise forms.ValidationError("Username is already taken.")
        return uname

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "Passwords do not match.")
        return cleaned


class AcceptInviteView(FormView):
    template_name = "accounts/accept_invite.html"
    form_class = AcceptInviteForm

    def dispatch(self, request, *args, **kwargs):
        # resolve the invite early and stop if it’s invalid.
        self.invite = get_object_or_404(Invite, token=kwargs["token"])
        if not self.invite.is_valid:
            return JsonResponse({"detail": "Invite expired or already used."}, status=400)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invite"] = self.invite
        return ctx

    def form_valid(self, form):
        # I create the user tied to the invite email, then bind the role.
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            email=self.invite.email,
            password=form.cleaned_data["password1"],
            display_name=form.cleaned_data.get("display_name", ""),
        )
        RoleBinding.objects.get_or_create(user=user, role=self.invite.role)

        # I mark the invite as accepted and record an audit event.
        self.invite.accepted_at = timezone.now()
        self.invite.save(update_fields=["accepted_at"])
        log_event(self.request, "invite.accepted", "Invite", self.invite.id)

        login(self.request, user)
        return redirect("/admin/")
