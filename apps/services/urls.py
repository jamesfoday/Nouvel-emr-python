# apps/services/urls.py
from django.urls import path
from . import views

app_name = "services"

urlpatterns = [
    # PUBLIC
    path("services/browse/", views.service_catalog, name="catalog"),
    path("services/all/", views.services_public_list, name="public_list"),
    path("services/<slug:slug>/", views.service_detail, name="detail"),

    # STAFF
    path("services/", views.service_list, name="list"),
    path("create/", views.service_create, name="create"),
    path("services/<slug:slug>/edit/", views.service_update, name="update"),
    path("services/<slug:slug>/delete/", views.service_delete, name="delete"),
]
