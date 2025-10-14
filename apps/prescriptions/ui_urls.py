# apps/prescriptions/ui_urls.py
from django.urls import path
from . import ui_views

app_name = "prescriptions_ui"

urlpatterns = [
    path("clinicians/<int:pk>/prescriptions/", ui_views.list_prescriptions, name="list"),
    path("clinicians/<int:pk>/prescriptions/new", ui_views.create_prescription, name="create"),
    path("clinicians/<int:pk>/prescriptions/<int:rx_id>/delete", ui_views.delete_prescription, name="delete"),
    path("clinicians/<int:pk>/prescriptions/<int:rx_id>", ui_views.view_prescription, name="view"),
]
