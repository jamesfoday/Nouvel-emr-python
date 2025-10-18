from django.urls import path
from . import ui_views
from . import ui_views as v

app_name = "encounters_ui"

urlpatterns = [
    path("clinicians/<int:pk>/encounters/", ui_views.list_encounters, name="list"),
    path("clinicians/<int:pk>/encounters/new", ui_views.create_encounter, name="create"),
    path("clinicians/<int:pk>/encounters/<int:eid>/", ui_views.view_encounter, name="view"),
    path("clinicians/<int:pk>/encounters/<int:eid>/close", ui_views.close_encounter, name="close"),

    # HTMX partials
    path("clinicians/<int:pk>/encounters/<int:eid>/save-vitals", ui_views.save_vitals, name="save_vitals"),
    path("clinicians/<int:pk>/encounters/<int:eid>/add-note", ui_views.add_note, name="add_note"),
    path(
        "clinicians/<int:pk>/encounters/<int:eid>/notes/<int:nid>/delete",
        v.delete_note,
        name="delete_note",
    ),
]
