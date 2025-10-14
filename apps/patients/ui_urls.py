# apps/patients/ui_urls.py
from django.urls import path
from . import ui_views as v

app_name = "patients_ui"

urlpatterns = [
    # Patients list + live search (HTMX)
    path("patients/", v.patients_home, name="patients_home"),
    path("patients/search/", v.patients_search, name="patients_search"),

    # Create new patient
    path("patients/create/", v.patients_create, name="patients_create"),

    # Detail / edit / deactivate
    path("patients/<int:pk>/", v.patient_detail, name="detail"),
    path("patients/<int:pk>/edit/", v.patients_edit, name="patients_edit"),
    path("patients/<int:pk>/deactivate/", v.patients_deactivate, name="patients_deactivate"),  # POST-only view

    # Staff-only: generate a one-time Set-Password URL
    path("patients/<int:pk>/login-link/", v.patients_login_link, name="patients_login_link"),

    # Merge helpers
    path("patients/merge/confirm/", v.merge_confirm, name="merge_confirm"),
    path("patients/merge/execute/", v.merge_execute, name="merge_execute"),

    # Compact patient picker (used by other modules)
    path("patients/pick/", v.pick_list, name="pick_list"),
]
