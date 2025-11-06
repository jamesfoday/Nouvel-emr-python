# config/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView

from django.contrib.auth import views as auth_views
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.views import PortalLoginView, StaffLoginView

urlpatterns = [
    # ---------- Site (public / home) ----------
    # Home now served by apps.core.urls (e.g., templates/home.html)
    
    path("", include(("apps.core.urls", "core"), namespace="core")),

    # Admin
    path("admin/", admin.site.urls),

    # Healthcheck
    path("health/", lambda r: JsonResponse({"ok": True}, status=200), name="health"),

    # OpenAPI schema + Swagger UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # JWT
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # ---------- v1 APIs ----------
    path("api/v1/", include(("apps.accounts.api_urls", "accounts_api"), namespace="accounts_api")),
    path("api/v1/", include(("apps.patients.api_urls", "patients_api"), namespace="patients_api")),
    path("api/v1/", include(("apps.appointments.api_urls", "appointments_api"), namespace="appointments_api")),

    # ---------- Legacy redirects ----------
    re_path(r"^api/accounts/(?P<rest>.*)$",
            RedirectView.as_view(url="/api/v1/accounts/%(rest)s", permanent=False)),
    re_path(r"^api/patients/(?P<rest>.*)$",
            RedirectView.as_view(url="/api/v1/patients/%(rest)s", permanent=False)),
    re_path(r"^api/appointments/(?P<rest>.*)$",
            RedirectView.as_view(url="/api/v1/appointments/%(rest)s", permanent=False)),

    # ---------- Console (UI) ----------
    path("console/", include(("apps.appointments.ui_urls", "appointments_ui"), namespace="appointments_ui")),
    path("console/", include(("apps.clinicians.ui_urls", "clinicians_ui"), namespace="clinicians_ui")),
    path("console/", include(("apps.prescriptions.ui_urls", "prescriptions_ui"), namespace="prescriptions_ui")),
    path("console/", include(("apps.documents.ui_urls", "documents_ui"), namespace="documents_ui")),
    path("console/", include(("apps.encounters.ui_urls", "encounters_ui"), namespace="encounters_ui")),
    path("console/", include(("apps.patients.ui_urls", "patients_ui"), namespace="patients_ui")),
    path("console/", include(("apps.labs.ui_urls", "labs_ui"), namespace="labs_ui")),

    # ---------- Portal (UI) ----------
    path("portal/", include(("apps.portal.ui_urls", "portal_ui"), namespace="portal_ui")),

    # ---------- Auth ----------
    path("login/",  PortalLoginView.as_view(), name="login"),
    # Role-aware staff logins
    path("reception/login/", StaffLoginView.as_view(audience="reception"), name="reception_login"),
    path("clinician/login/", StaffLoginView.as_view(audience="clinician"), name="clinician_login"),
    path("console/login/",  StaffLoginView.as_view(audience="clinician"), name="console_login"),  # optional alias

    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("password-reset/", auth_views.PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(success_url="/reset/done/"),
        name="password_reset_confirm",
    ),
    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(extra_context={"login_url": "/login/"}),
        name="password_reset_complete",
    ),

    # Other apps
    path("reception/", include("apps.reception.ui_urls")),
    path("services/", include(("apps.services.urls", "services"), namespace="services")),
    path("console/subscriptions/", include(("apps.subscriptions.urls", "subscriptions"), namespace="subscriptions")),
    path("healthplans/", include(("apps.healthplans.urls", "healthplans"), namespace="healthplans")),
    path("invoices/", include("apps.invoices.urls")),
    path("inquiry/", include("apps.inquiry.urls")),
    path("bugs/", include("apps.bugtracker.urls")),
    path("", include("apps.menus.urls", namespace="menus")),
    # path("accounts/", include("django.contrib.auth.urls")),
    
]

# Media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
