# apps/appointments/urls.py
from django.urls import path
from . import views

app_name = "appointments"

urlpatterns = [
    path("create/", views.appointment_create, name="create"),
    path("check/", views.check_conflict, name="check"),
]
