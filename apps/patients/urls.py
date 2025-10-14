from django.urls import path
from . import views

app_name = "patients"
urlpatterns = [
    path("search/", views.search, name="search"),
]