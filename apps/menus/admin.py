# menus/admin.py
from django.contrib import admin
from .models import Menu, MenuItem

class ChildrenInline(admin.TabularInline):
    model = MenuItem
    fk_name = "parent"
    extra = 0
    fields = ("label", "url_kind", "named_url", "internal_path", "external_url", "order", "is_active")
    show_change_link = True

@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("label", "menu", "parent", "url_kind", "order", "is_active", "visibility", "is_mega", "mega_columns")
    list_filter  = ("menu", "url_kind", "is_active", "visibility", "is_mega")
    fields = (
        "menu", "parent", "label", "icon", "order", "is_active", "visibility",
        "url_kind", "named_url", "url_kwargs", "url_query",
        "internal_path", "external_url", "open_in_new_tab",
        "is_mega", "mega_columns",
    )


@admin.register(Menu)
class MenuAdmin(admin.ModelAdmin):
    list_display = ("name", "key", "is_active")
    search_fields = ("name", "key")
