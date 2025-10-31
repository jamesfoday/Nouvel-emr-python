# apps/services/admin.py
from django.contrib import admin
from .models import Service, ServiceSection, ServiceCategory

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "order", "is_public")
    list_editable = ("order", "is_public",)
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


