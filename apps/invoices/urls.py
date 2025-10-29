from django.urls import path
from . import views

app_name = "invoices"

urlpatterns = [
    path("", views.invoice_list, name="list"),
    path("create/", views.invoice_create, name="create"),
    path("<int:pk>/", views.invoice_detail, name="detail"),
    path("<int:pk>/edit/", views.invoice_update, name="edit"),
    path("<int:pk>/delete/", views.invoice_delete, name="delete"),
    path("<int:pk>/pdf/", views.invoice_pdf, name="pdf"),
]