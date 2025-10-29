# menus/urls.py
from django.urls import path
from . import views

app_name = "menus"

urlpatterns = [
    # Menus
    path("dashboard/menus/", views.MenuListView.as_view(), name="menu_list"),
    path("dashboard/menus/create/", views.MenuCreateView.as_view(), name="menu_create"),
    path("dashboard/menus/<int:pk>/", views.MenuDetailView.as_view(), name="menu_detail"),
    path("dashboard/menus/<int:pk>/edit/", views.MenuUpdateView.as_view(), name="menu_edit"),
    path("dashboard/menus/<int:pk>/delete/", views.MenuDeleteView.as_view(), name="menu_delete"),

    # Menu Items
    path("dashboard/menus/<int:menu_id>/items/create/", views.MenuItemCreateView.as_view(), name="item_create"),
    path("dashboard/menus/items/<int:pk>/edit/", views.MenuItemUpdateView.as_view(), name="item_edit"),
    path("dashboard/menus/items/<int:pk>/delete/", views.MenuItemDeleteView.as_view(), name="item_delete"),
]
