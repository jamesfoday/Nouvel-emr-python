# apps/appointments/ui_urls.py
from django.urls import path
from . import ui_views

app_name = "appointments_ui"

urlpatterns = [
    # /console/appointments/
    path("appointments/", ui_views.appointments_home, name="console_appointments"),

    # Modal + HTMX flows
    # /console/appointments/book?patient_id=123
    path("appointments/book", ui_views.book_dialog, name="console_book_modal"),

    # /console/appointments/free-slots?clinician_id=...&date=YYYY-MM-DD&duration=30
    path("appointments/free-slots", ui_views.slots_for_day, name="console_free_slots"),

    # POST from the slot list to create the appointment
    path("appointments/create", ui_views.create_from_slot, name="console_create_appointment"),
]
