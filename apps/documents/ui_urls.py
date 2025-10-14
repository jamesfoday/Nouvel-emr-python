# apps/documents/ui_urls.py
from django.urls import path
from . import ui_views

app_name = "documents_ui"

urlpatterns = [
    path("clinicians/<int:pk>/documents/", ui_views.list_documents, name="list"),
    path("clinicians/<int:pk>/documents/upload", ui_views.upload_document, name="upload"),
    path("clinicians/<int:pk>/documents/<int:doc_id>/delete", ui_views.delete_document, name="delete"),
    path("clinicians/<int:pk>/documents/<int:doc_id>", ui_views.view_document, name="view"),
]
