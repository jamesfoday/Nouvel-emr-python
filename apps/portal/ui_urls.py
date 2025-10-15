# apps/portal/ui_urls.py
from django.urls import path
from . import ui_views as v
from . import ui_views as pv

app_name = "portal_ui"

urlpatterns = [
    path("", v.dashboard, name="home"),
    path("profile/", v.profile, name="profile"),
    path("profile/update/", v.profile_update, name="profile_update"),

    # Cards/panels on the dashboard
    path("appts/panel/", v.appts_panel, name="appts_panel"),
    path("documents/panel/", v.documents_panel, name="documents_panel"),
    path("tests/panel/", v.tests_panel, name="tests_panel"),
    path("rx/panel/", v.rx_panel, name="rx_panel"),

    # Messaging (patient side)
    path("messages/panel/", v.messages_panel, name="messages_panel"),
    path("messages/thread/", v.messages_thread, name="messages_thread"),
    path("messages/send/", v.messages_send, name="messages_send"),
    path("messages/chat/", v.messages_chat, name="messages_chat"),

    # NEW: tiny navbar badge (patient total unread)
    path("messages/badge/", v.unread_total_badge, name="unread_total_badge"),

    # Admin impersonation helpers
    path("as/<int:patient_id>/", v.dashboard_as, name="dashboard_as"),
    path("as/stop/", v.dashboard_stop_impersonate, name="dashboard_stop_impersonate"),
    path("appts/", v.appts_list, name="appts_list"),

    path("consultations/book/", pv.book_appt_page, name="book_appt"),
    path("consultations/book/slots/", pv.book_appt_slots, name="book_appt_slots"),
    path("consultations/book/create/", pv.book_appt_create, name="book_appt_create"),
     # --- Calendar booking (week grid) ---
    path("consultations/book/calendar/", pv.book_appt_calendar, name="book_appt_calendar"),
    path("consultations/book/slots-grid/", pv.book_appt_slots_grid, name="book_appt_slots_grid"),

    path("prescriptions/", pv.portal_rx_list, name="rx_list"),
    path("prescriptions/<int:rx_id>/", pv.portal_rx_detail, name="rx_detail"),
    path("prescriptions/<int:rx_id>/download/", pv.portal_rx_download, name="rx_download"),

    path("documents/", pv.docs_list, name="docs_list"),
    path("documents/<int:doc_id>/", pv.doc_detail, name="doc_detail"),
    path("documents/<int:doc_id>/download/", pv.docs_download, name="docs_download"),
    path("documents/<int:doc_id>/modal/", pv.docs_view_modal, name="docs_view_modal"),
]