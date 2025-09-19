from django.urls import path
from .ui_views import console_home, patients_home, patients_search

app_name = "patients_ui"

urlpatterns = [
    path("", console_home, name="console_home"),
    path("patients/", patients_home, name="patients_home"),
    path("patients/search", patients_search, name="patients_search"),
]
