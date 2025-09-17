from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import PatientViewSet

app_name = "patients_api"

router = DefaultRouter()
router.register(r"patients", PatientViewSet, basename="patient")

urlpatterns = [
    path("", include(router.urls)),
]
