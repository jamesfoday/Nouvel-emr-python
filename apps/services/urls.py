from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    path("browse/", views.service_catalog, name="catalog"),

    # ---------- Management (staff) ----------
    path("", views.service_list, name="list"),
    path("create/", views.service_create, name="create"),

    # Edit — keep existing name 'edit' AND provide alias 'update' for templates
    path("<slug:slug>/edit/", views.service_update, name="edit"),
    path("<slug:slug>/edit/", views.service_update, name="update"),

    path("<slug:slug>/delete/", views.service_delete, name="delete"),

    # ---------- Public detail ----------
    path("<slug:slug>/", views.service_detail, name="detail"),
]
