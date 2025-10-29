# apps/accounts/admin.py
from __future__ import annotations

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import User, Invite, ReceptionistProfile


# -------------------------
# Inline for ReceptionistProfile
# -------------------------
class ReceptionistProfileInline(admin.StackedInline):
    model = ReceptionistProfile
    can_delete = False
    extra = 0
    fk_name = "user"
    fieldsets = (
        (None, {
            "fields": ("avatar", "title", "phone", "department", "location", "bio"),
        }),
    )


# -------------------------
# Custom User admin (single registration)
# -------------------------
@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """
    Custom admin for AUTH_USER_MODEL:
    - Keep Django auth features
    - Add display_name + avatar fields
    - Show avatar thumbnails in list + preview on form
    - Include ReceptionistProfile inline for quick receptionist creation
    """
    # List view
    list_display = ("id", "avatar_thumb", "username", "email", "display_name", "is_staff", "is_active")
    search_fields = ("username", "email", "first_name", "last_name", "display_name")
    ordering = ("id",)

    # Fieldsets on change form
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "email", "display_name", "avatar", "avatar_preview")}),
        (_("Permissions"), {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )

    # Fieldsets on add form
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "password1", "password2", "email", "first_name", "last_name", "display_name", "avatar"),
        }),
    )

    # Read-only preview
    readonly_fields = ("avatar_preview",)

    # Inline profile
    inlines = [ReceptionistProfileInline]

    # Helpers
    def avatar_thumb(self, obj: User):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width:32px;height:32px;object-fit:cover;border-radius:50%;border:1px solid #ddd;" />',
                obj.avatar.url,
            )
        return "—"
    avatar_thumb.short_description = "Avatar"

    def avatar_preview(self, obj: User):
        if obj.avatar:
            return format_html(
                '<img src="{}" style="width:80px;height:80px;object-fit:cover;border-radius:50%;border:1px solid #ddd;" />',
                obj.avatar.url,
            )
        return "—"
    avatar_preview.short_description = "Preview"


# -------------------------
# Invite admin
# -------------------------
@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ("id", "email", "role", "expires_at", "accepted_at", "accept_link", "created_at")
    list_filter = ("role", "accepted_at")
    search_fields = ("email",)
    ordering = ("-created_at",)

    def accept_link(self, obj: Invite):
        """Render a relative URL to accept the invite (if route exists)."""
        try:
            url = reverse("accounts:accept_invite", args=[obj.token])
            return format_html('<a href="{}">Open</a>', url)
        except Exception:
            return obj.token
    accept_link.short_description = "Accept URL"



@admin.register(ReceptionistProfile)
class ReceptionistProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "title", "phone", "department", "location")
    search_fields = ("user__username", "user__first_name", "user__last_name", "phone", "department", "location")
