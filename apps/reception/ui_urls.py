from django.urls import path
from . import ui_views

app_name = "reception"

urlpatterns = [
    # Dashboard & profile
    path("", ui_views.receptionist_dashboard, name="dashboard"),
    path("profile/", ui_views.receptionist_profile_edit, name="profile_edit"),

    # Appointments hub
    path("appointments/", ui_views.appt_hub_clinicians, name="appt_hub"),
    path("appointments/clinicians/", ui_views.appt_hub_clinicians, name="appt_hub_clinicians"),
    path("appointments/clinicians/<int:cid>/", ui_views.appt_hub_for_clinician, name="appt_hub_for_clinician"),

    #  Availability panel (the missing route)
    path(
        "appointments/clinicians/<int:cid>/availability/",
        ui_views.clinician_availability_panel,
        name="clinician_availability",
    ),
    # Legacy alias in case any template uses singular “clinician”
    path(
        "appointments/clinician/<int:cid>/availability/",
        ui_views.clinician_availability_panel,
        name="clinician_availability_legacy",
    ),

    # Quick actions
    path("appointments/<int:pk>/remind/", ui_views.appt_remind, name="appt_remind"),
    path("appointments/<int:pk>/cancel/", ui_views.appt_cancel, name="appt_cancel"),

    # Reception booking (week view)
    path("appointments/book/", ui_views.reception_book_calendar, name="reception_book_calendar"),
    path("appointments/book/slots/", ui_views.reception_book_slots_grid, name="reception_book_slots_grid"),
    path("appointments/book/create/", ui_views.reception_book_create, name="reception_book_create"),

    # Alias so `{% url 'reception:book_calendar' %}` continues to work
    path("appointments/book/", ui_views.reception_book_calendar, name="book_calendar"),

    # Typeahead
    path("patients/typeahead/", ui_views.patient_typeahead, name="patient_typeahead"),
    path("inquiry/<int:pk>/", ui_views.inquiry_modal, name="inquiry_view"),
    path("dm/thread/", ui_views.dm_thread, name="dm_thread"),
    path("dm/send/",   ui_views.dm_send,   name="dm_send"),
]
