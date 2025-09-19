from django.urls import path
from .ui_views import book_dialog, slots_for_day, create_from_slot

app_name = "appointments_ui"

urlpatterns = [
    path("appointments/book", book_dialog, name="book_dialog"),
    path("appointments/slots", slots_for_day, name="slots_for_day"),
    path("appointments/create", create_from_slot, name="create_from_slot"),
]
