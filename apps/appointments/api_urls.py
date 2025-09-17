from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api import AppointmentViewSet

app_name = "appointments_api"

router = DefaultRouter()
router.register(r"appointments", AppointmentViewSet, basename="appointment")

urlpatterns = [path("", include(router.urls))]
