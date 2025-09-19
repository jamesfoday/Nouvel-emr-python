# config/urls.py
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.views.generic import RedirectView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    # Home → Swagger
    path("", RedirectView.as_view(url="/api/docs/", permanent=False), name="home"),

    # Admin
    path("admin/", admin.site.urls),

    # Healthcheck
    path("health/", lambda r: JsonResponse({"ok": True}, status=200)),

    # OpenAPI schema + Swagger UI
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),

    # JWT (pairs with Session auth for admin/Swagger)
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # ---------- v1 APIs (ONE include per app with a unique namespace) ----------
    path("api/v1/", include(("apps.accounts.api_urls", "accounts_api"), namespace="accounts_api")),
    path("api/v1/", include(("apps.patients.api_urls", "patients_api"), namespace="patients_api")),
    path("api/v1/", include(("apps.appointments.api_urls", "appointments_api"), namespace="appointments_api")),

    # ---------- Legacy redirects (no duplicate namespaces) ----------
    # Keep older paths working without re-including the same URLConfs.
    re_path(r"^api/accounts/(?P<rest>.*)$",
            RedirectView.as_view(url="/api/v1/accounts/%(rest)s", permanent=False)),
    re_path(r"^api/patients/(?P<rest>.*)$",
            RedirectView.as_view(url="/api/v1/patients/%(rest)s", permanent=False)),
    re_path(r"^api/appointments/(?P<rest>.*)$",
            RedirectView.as_view(url="/api/v1/appointments/%(rest)s", permanent=False)),

    # Console (your minimal UI)
    path("console/", include("apps.patients.ui_urls")),
    path("console/", include("apps.appointments.ui_urls")),
]
