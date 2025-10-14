# apps/clinicians/ui_urls.py
from django.urls import path
from . import ui_views as v

app_name = "clinicians_ui"

urlpatterns = [
    # ---------- Superuser utilities ----------
    path("clinicians/", v.list_clinicians, name="list"),

    # ---------- Dashboard & sections ----------
    path("clinicians/<int:pk>/dashboard/",      v.dashboard,          name="dashboard"),
    path("clinicians/<int:pk>/consultations/",  v.consultations_all,  name="consultations_all"),
    path("clinicians/<int:pk>/upcoming/",       v.upcoming,           name="upcoming"),

    # Tests (small card + full index + HTMX table)
    path("clinicians/<int:pk>/tests/",          v.tests,              name="tests"),
    path("clinicians/<int:pk>/tests/index/",    v.tests_index,        name="tests_index"),
    path("clinicians/<int:pk>/tests/table/",    v.tests_table,        name="tests_table"),

    # ---------- Inbox / Direct Messages ----------
    path("clinicians/<int:pk>/inbox/",          v.inbox,              name="inbox"),
    path("clinicians/<int:pk>/dm/",             v.direct_messages,    name="direct_messages"),
    path("clinicians/<int:pk>/dm/thread/",      v.dm_thread,          name="dm_thread"),
    path("clinicians/<int:pk>/dm/send/",        v.dm_send,            name="dm_send"),

    # ---------- Appointments actions ----------
    path(
        "clinicians/<int:pk>/appt/<int:appt_pk>/cancel/",
        v.cancel_appt,
        name="cancel_appt",
    ),

    # ---------- Profile ----------
    path("clinicians/<int:pk>/profile/edit/",   v.edit_profile,       name="edit_profile"),

    # ---------- NEW: navbar unread badge ----------
    path("clinicians/<int:pk>/messages/badge/", v.unread_badge,       name="unread_badge"),

    path("clinicians/<int:pk>/availability/",                  v.availability_index,          name="availability_index"),
    path("clinicians/<int:pk>/availability/list/",             v.availability_list_partial,   name="availability_list_partial"),
    path("clinicians/<int:pk>/availability/preview/",          v.availability_preview_partial,name="availability_preview_partial"),
    path("clinicians/<int:pk>/availability/new/",              v.availability_new,            name="availability_new"),
    path("clinicians/<int:pk>/availability/<int:avail_id>/",   v.availability_edit,           name="availability_edit"),
    path("clinicians/<int:pk>/availability/<int:avail_id>/delete/", v.availability_delete,   name="availability_delete"),
    path("clinicians/<int:pk>/requests/approve/<int:appt_id>/", v.approve_request, name="approve_request"),
    path("clinicians/<int:pk>/requests/decline/<int:appt_id>/", v.decline_request, name="decline_request"),

   

]