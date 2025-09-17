from django.contrib import admin
from django.http import JsonResponse
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

def health(_request):
    return JsonResponse({"status": "ok"})

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
     path("api/v1/auth/", include("apps.accounts.api_urls", namespace="accounts_api")),
      path("api/v1/", include("apps.patients.api_urls", namespace="patients_api")),
      path("api/auth/", include("apps.accounts.api_urls", namespace="auth_api")),
      path("api/v1/", include("apps.appointments.api_urls", namespace="appointments_api")),

]
