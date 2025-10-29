# apps/accounts/views.py
from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, get_user_model
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.generic import FormView, TemplateView
from django.urls import reverse

from .models import Invite
from apps.rbac.models import RoleBinding
from ..audit.utils import log_event

# ----------------------- Patient Portal Login (email OR phone) -----------------------
class PortalLoginForm(forms.Form):
    identifier = forms.CharField(
        required=True,
        label="Email or phone",
        widget=forms.TextInput(attrs={"autocomplete": "username", "placeholder": "you@example.com or +1 555 123 4567"}),
    )
    password = forms.CharField(
        required=True,
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "••••••••"}),
    )
    remember_me = forms.BooleanField(required=False, initial=True)


class PortalLoginView(TemplateView):
    template_name = "portal/login.html"

    def get(self, request, *args, **kwargs):
        form = PortalLoginForm(initial={"remember_me": True})
        return render(request, self.template_name, {"form": form, "next": request.GET.get("next", "")})

    def post(self, request, *args, **kwargs):
        form = PortalLoginForm(request.POST or None)
        next_url = request.POST.get("next") or request.GET.get("next") or getattr(settings, "LOGIN_REDIRECT_URL", "/portal/")
        if not form.is_valid():
            messages.error(request, "Please fill in both fields.")
            return render(request, self.template_name, {"form": form, "next": next_url})

        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        remember = form.cleaned_data.get("remember_me", True)

        # Resolve identifier → user (email first, else phone via Patient link)
        User = get_user_model()
        user = None
        if "@" in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            try:
                from apps.patients.models import Patient
                pat = Patient.objects.filter(phone__iexact=identifier).select_related("user").first()
                user = getattr(pat, "user", None)
            except Exception:
                user = None

        if not user:
            messages.error(request, "Invalid credentials.")
            return render(request, self.template_name, {"form": form, "next": next_url})

        auth_user = authenticate(request, username=user.username, password=password)
        if not auth_user:
            messages.error(request, "Invalid credentials.")
            return render(request, self.template_name, {"form": form, "next": next_url})

        login(request, auth_user)
        if not remember:
            request.session.set_expiry(0)  # expire at browser close

        if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            next_url = getattr(settings, "LOGIN_REDIRECT_URL", "/portal/")
        messages.success(request, "Welcome back 👋")
        return redirect(next_url)


# ----------------------- Accept Invite -----------------------
class AcceptInviteForm(forms.Form):
    username = forms.CharField(max_length=150)
    display_name = forms.CharField(max_length=150, required=False)
    password1 = forms.CharField(widget=forms.PasswordInput)
    password2 = forms.CharField(widget=forms.PasswordInput)

    def clean_username(self):
        uname = self.cleaned_data["username"]
        if get_user_model().objects.filter(username=uname).exists():
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
        self.invite = get_object_or_404(Invite, token=kwargs["token"])
        if not self.invite.is_valid:
            return JsonResponse({"detail": "Invite expired or already used."}, status=400)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["invite"] = self.invite
        return ctx

    def form_valid(self, form):
        User = get_user_model()
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            email=self.invite.email,
            password=form.cleaned_data["password1"],
            **({"display_name": form.cleaned_data.get("display_name")} if "display_name" in User._meta.fields_map else {}),
        )
        RoleBinding.objects.get_or_create(user=user, role=self.invite.role)
        self.invite.accepted_at = timezone.now()
        self.invite.save(update_fields=["accepted_at"])
        log_event(self.request, "invite.accepted", "Invite", self.invite.id)
        login(self.request, user)
        return redirect("/admin/")


# ----------------------- Staff Login (Reception & Clinician) -----------------------
class StaffLoginView(PortalLoginView):
    """
    Reuses PortalLoginView (identifier + password + remember_me),
    but redirects to the correct home based on `audience`: 'reception' or 'clinician'.
    """
    template_name = "auth/login_staff.html"
    audience = None  # set by as_view(audience="reception"|"clinician")

    def get(self, request, *args, **kwargs):
        # Same as portal, but render staff template and pass 'audience'
        form = PortalLoginForm(initial={"remember_me": True})
        return render(
            request,
            self.template_name,
            {"form": form, "next": request.GET.get("next", ""), "audience": self.audience or "staff"},
        )

    def post(self, request, *args, **kwargs):
        """
        Copy of PortalLoginView.post, but picks a staff destination instead of /portal/.
        """
        form = PortalLoginForm(request.POST or None)
        # Read next but don't default to portal; we'll compute a staff default below.
        next_url = request.POST.get("next") or request.GET.get("next") or ""
        if not form.is_valid():
            messages.error(request, "Please fill in both fields.")
            return render(request, self.template_name, {"form": form, "next": next_url, "audience": self.audience or "staff"})

        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]
        remember = form.cleaned_data.get("remember_me", True)

        User = get_user_model()
        user = None
        if "@" in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
        if user is None:
            try:
                from apps.patients.models import Patient
                pat = Patient.objects.filter(phone__iexact=identifier).select_related("user").first()
                user = getattr(pat, "user", None)
            except Exception:
                user = None

        if not user:
            messages.error(request, "Invalid credentials.")
            return render(request, self.template_name, {"form": form, "next": next_url, "audience": self.audience or "staff"})

        auth_user = authenticate(request, username=user.username, password=password)
        if not auth_user:
            messages.error(request, "Invalid credentials.")
            return render(request, self.template_name, {"form": form, "next": next_url, "audience": self.audience or "staff"})

        login(request, auth_user)
        if not remember:
            request.session.set_expiry(0)

        # Safe next= (same-origin) and NOT pointing to the patient portal root
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
            if not next_url.rstrip("/").endswith("/portal"):
                messages.success(request, "Welcome back 👋")
                return redirect(next_url)

        # Choose a staff default destination
        if self.audience == "reception":
            try:
                url = reverse("reception:dashboard")
            except Exception:
                url = "/reception/"
        elif self.audience == "clinician":
            url = None
            # Prefer existing, no-pk console endpoints
            for name in (
                "clinicians_ui:list",                    # /console/clinicians/
                "appointments_ui:console_appointments",  # /console/appointments/
                "patients_ui:list",                      # /console/patients/
            ):
                try:
                    url = reverse(name)
                    break
                except Exception:
                    continue
            if not url:
                url = "/console/clinicians/"  # safe hard fallback
        else:
            url = "/console/clinicians/dashboard"  # generic staff fallback

        messages.success(request, "Welcome back 👋")
        return redirect(url)
